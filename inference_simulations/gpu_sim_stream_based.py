"""
gpu_sim_stream_based.py

A discrete-event simulation of how a real GPU actually schedules and runs
work, modeling the hardware hierarchy the way it really behaves:

    Stream (an in-order queue of kernel launches, host-side)
        -> Kernel (one GPU operation = a grid of thread blocks)
            -> ThreadBlock (assigned to exactly ONE SM, for its whole life --
                             a block never spans multiple SMs, because shared
                             memory and __syncthreads() only work within one SM)
                -> occupies some number of that SM's resident warp slots
                   until it finishes

Different STREAMS can have kernels running *concurrently*, sharing the same
pool of SMs -- a block from stream 0 and a block from stream 1 can be
resident on different SMs (or, if there's room, the same GPU) at the same
simulated instant. Kernels *within* one stream, however, run strictly one
after another -- that's the actual semantics of a CUDA stream.

Why discrete-event instead of real threads (as gpu_sim.py used):
  - real warp lanes execute in lockstep (SIMT) -- they are not independently
    scheduled the way OS threads are, so modeling them with real threads
    misrepresents the very thing being simulated
  - a realistic config (100+ SMs x dozens of resident warps each) would mean
    spinning up thousands of real OS threads just for bookkeeping arithmetic
  - a discrete-event loop (a priority queue of "at time T, X happens"
    events) gives exact, reproducible timing, no GIL contention, and scales
    to any SM/warp count for free

This file deliberately stops at "how does a batch's work get decomposed into
blocks and scheduled onto SMs, and how long does that take" -- it does NOT
model attention or FlashAttention. The extension point is ThreadBlock's
`flops` / `bytes_transferred` fields (set via submit_kernel's parameters):
swap in real attention-shaped numbers there later.
"""

from __future__ import annotations

import heapq
import itertools
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Hardware config
# ---------------------------------------------------------------------------
@dataclass
class GPUHardwareConfig:
    """
    GPU-wide numbers, the way a real spec sheet states them -- FLOPs and
    memory bandwidth are totals for the whole chip, not per-SM. Compute is
    parallel per-SM (each SM has its own ALUs/tensor cores), so we divide
    the FLOPs budget evenly across SMs; memory bandwidth is a genuinely
    shared, chip-wide resource (one HBM bus), so it is NOT divided per-SM
    here -- every block's memory time is computed against the full shared
    bandwidth. (This sim does not model bandwidth *contention* between
    concurrently-running blocks -- see the module docstring notes on scope.)
    """
    num_sms: int
    max_resident_warps_per_sm: int   # occupancy limit -- real GPUs cap this (e.g. ~64 warps/SM)
    total_flops_per_sec: float       # GPU-wide peak FLOPs/sec
    total_memory_bandwidth: float    # GPU-wide peak bytes/sec (HBM)
    mfu: float                       # model FLOPs utilization: fraction of peak actually achieved
    mbu: float                       # memory bandwidth utilization: same idea, for memory

    @property
    def flops_per_sec_per_sm(self) -> float:
        return (self.total_flops_per_sec * self.mfu) / self.num_sms

    @property
    def effective_memory_bandwidth(self) -> float:
        return self.total_memory_bandwidth * self.mbu

    @classmethod
    def default(cls) -> "GPUHardwareConfig":
        # Loosely A100-shaped magnitudes -- not literal spec values, just plausible.
        return cls(
            num_sms=108,
            max_resident_warps_per_sm=64,
            total_flops_per_sec=312e12,
            total_memory_bandwidth=2.0e12,
            mfu=0.4,
            mbu=0.6,
        )


# ---------------------------------------------------------------------------
# The unit of work a real GPU actually schedules onto hardware: a thread block
# ---------------------------------------------------------------------------
@dataclass
class ThreadBlock:
    block_id: int
    kernel: "Kernel"
    num_warps: int            # occupies this many of an SM's resident-warp budget
    flops: float               # total FLOPs this block must perform
    bytes_transferred: float   # total bytes this block must move to/from HBM

    def duration_on_sm(self, config: GPUHardwareConfig) -> float:
        """
        Roofline model: wall-clock time is set by whichever of compute or
        memory is the bottleneck, not their sum -- real hardware overlaps
        compute with memory transfer rather than paying for both serially.
        """
        compute_time = self.flops / config.flops_per_sec_per_sm
        memory_time = self.bytes_transferred / config.effective_memory_bandwidth
        return max(compute_time, memory_time)


# ---------------------------------------------------------------------------
# A kernel: one GPU operation, decomposed into a grid of thread blocks
# ---------------------------------------------------------------------------
@dataclass
class Kernel:
    kernel_id: int
    name: str
    stream_id: int
    blocks: list[ThreadBlock] = field(default_factory=list)
    blocks_remaining: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    @property
    def duration(self) -> Optional[float]:
        if self.start_time is None or self.end_time is None:
            return None
        return self.end_time - self.start_time


# ---------------------------------------------------------------------------
# A stream: an in-order queue of kernels. Different streams run concurrently;
# kernels WITHIN one stream run strictly one after another.
# ---------------------------------------------------------------------------
class Stream:
    def __init__(self, stream_id: int):
        self.stream_id = stream_id
        self.pending_kernels: deque[Kernel] = deque()
        self.active_kernel: Optional[Kernel] = None

    def enqueue(self, kernel: Kernel) -> None:
        self.pending_kernels.append(kernel)

    def has_ready_kernel(self) -> bool:
        return self.active_kernel is None and len(self.pending_kernels) > 0

    def pop_next(self) -> Kernel:
        kernel = self.pending_kernels.popleft()
        self.active_kernel = kernel
        return kernel

    def finish_active(self) -> None:
        self.active_kernel = None


# ---------------------------------------------------------------------------
# One SM: tracks how many warps are currently resident (occupied)
# ---------------------------------------------------------------------------
class SM:
    def __init__(self, sm_id: int, config: GPUHardwareConfig):
        self.sm_id = sm_id
        self.config = config
        self.resident_warps = 0
        self.resident_blocks: dict[int, ThreadBlock] = {}
        # Warp-seconds, not raw seconds: multiple blocks can be resident on
        # this SM *concurrently* (different warp slots), so summing their
        # durations directly would double-count overlapping time. Tracking
        # duration * num_warps instead gives true warp-occupancy, which is
        # mathematically capped at max_resident_warps_per_sm * elapsed_time
        # since admission never oversubscribes the SM.
        self.busy_warp_seconds = 0.0

    def free_warp_slots(self) -> int:
        return self.config.max_resident_warps_per_sm - self.resident_warps

    def can_admit(self, block: ThreadBlock) -> bool:
        return self.free_warp_slots() >= block.num_warps

    def admit(self, block: ThreadBlock) -> None:
        self.resident_warps += block.num_warps
        self.resident_blocks[block.block_id] = block

    def retire(self, block: ThreadBlock, duration: float) -> None:
        self.resident_warps -= block.num_warps
        del self.resident_blocks[block.block_id]
        self.busy_warp_seconds += duration * block.num_warps


# ---------------------------------------------------------------------------
# The GPU: owns the SM pool and the streams, and drives the discrete-event loop
# ---------------------------------------------------------------------------
class GPUStreamSim:
    """
    submit_kernel() enqueues work; run_until_idle() drains the whole event
    queue in simulated-time order. There is exactly one logical clock
    (self.clock); nothing here uses real wall-clock time or real threads.
    """

    def __init__(self, config: GPUHardwareConfig):
        self.config = config
        self.sms: list[SM] = [SM(i, config) for i in range(config.num_sms)]
        self.streams: dict[int, Stream] = {}
        self.clock = 0.0
        self.completed_kernels: list[Kernel] = []
        self.pending_blocks: list[ThreadBlock] = []  # blocks whose kernel has started but that aren't on an SM yet

        self._event_queue: list[tuple[float, int, str, object]] = []
        # A monotonically increasing tie-breaker so heapq never has to compare
        # `kind`/`payload` directly when two events land at the exact same
        # simulated time (those aren't orderable against each other).
        self._event_seq = itertools.count()
        self._kernel_id_seq = itertools.count()
        self._block_id_seq = itertools.count()

    # -- public API -------------------------------------------------------

    def get_or_create_stream(self, stream_id: int) -> Stream:
        if stream_id not in self.streams:
            self.streams[stream_id] = Stream(stream_id)
        return self.streams[stream_id]

    def submit_kernel(
        self,
        stream_id: int,
        name: str,
        num_blocks: int,
        warps_per_block: int,
        flops_per_block: float,
        bytes_per_block: float,
    ) -> Kernel:
        """
        Build a kernel's launch grid (num_blocks identical blocks, for
        simplicity) and enqueue it on the given stream. This is the
        extension point for attention/FlashAttention later: compute
        flops_per_block / bytes_per_block from real tile math (and vary
        them per block if you want non-uniform tiles) instead of passing
        flat numbers.
        """
        kernel = Kernel(kernel_id=next(self._kernel_id_seq), name=name, stream_id=stream_id)
        for _ in range(num_blocks):
            kernel.blocks.append(
                ThreadBlock(
                    block_id=next(self._block_id_seq),
                    kernel=kernel,
                    num_warps=warps_per_block,
                    flops=flops_per_block,
                    bytes_transferred=bytes_per_block,
                )
            )
        kernel.blocks_remaining = num_blocks

        stream = self.get_or_create_stream(stream_id)
        stream.enqueue(kernel)
        self._schedule_event(self.clock, "kernel_arrived", stream_id)
        return kernel

    def run_until_idle(self) -> list[Kernel]:
        """Process every event in simulated-time order until none remain."""
        while self._event_queue:
            time_, _, kind, payload = heapq.heappop(self._event_queue)
            self.clock = time_
            if kind == "kernel_arrived":
                self._try_start_next_kernel(payload)
            elif kind == "block_finished":
                sm_id, block = payload
                self._on_block_finished(sm_id, block)
        return self.completed_kernels

    def summary(self) -> str:
        """Basic GPU stats derivable straight from the event trace we already kept."""
        if not self.completed_kernels:
            return "no kernels completed"
        makespan = max(k.end_time for k in self.completed_kernels) - min(k.start_time for k in self.completed_kernels)
        lines = [f"makespan: {makespan:.4f}s across {len(self.completed_kernels)} kernel(s)"]
        for sm in self.sms:
            if sm.busy_warp_seconds > 0:
                capacity_warp_seconds = makespan * self.config.max_resident_warps_per_sm
                occupancy_pct = 100 * sm.busy_warp_seconds / capacity_warp_seconds
                lines.append(f"  SM {sm.sm_id}: warp-occupancy {occupancy_pct:.1f}% of makespan")
        return "\n".join(lines)

    # -- internal scheduling logic -----------------------------------------

    def _schedule_event(self, time_: float, kind: str, payload) -> None:
        heapq.heappush(self._event_queue, (time_, next(self._event_seq), kind, payload))

    def _try_start_next_kernel(self, stream_id: int) -> None:
        stream = self.streams[stream_id]
        if not stream.has_ready_kernel():
            return
        kernel = stream.pop_next()
        kernel.start_time = self.clock
        print(f"[t={self.clock:.5f}] stream {stream_id}: kernel '{kernel.name}' (id={kernel.kernel_id}) starts -- {len(kernel.blocks)} blocks")
        self.pending_blocks.extend(kernel.blocks)
        self._admit_pending_blocks()

    def _admit_pending_blocks(self) -> None:
        """
        Greedily place as many pending blocks (from ANY kernel/stream that
        has started) onto ANY SM with room as currently fit. This is where
        "streams share the GPU" actually shows up: blocks from different
        streams compete for the same pool of free SM capacity here.
        """
        still_pending: list[ThreadBlock] = []
        for block in self.pending_blocks:
            admitted = False
            for sm in self.sms:
                if sm.can_admit(block):
                    sm.admit(block)
                    duration = block.duration_on_sm(self.config)
                    finish_time = self.clock + duration
                    print(
                        f"[t={self.clock:.5f}]   block {block.block_id} "
                        f"(kernel {block.kernel.kernel_id} '{block.kernel.name}', stream {block.kernel.stream_id}) "
                        f"-> SM {sm.sm_id} ({block.num_warps} warps), finishes t={finish_time:.5f}"
                    )
                    self._schedule_event(finish_time, "block_finished", (sm.sm_id, block))
                    admitted = True
                    break
            if not admitted:
                still_pending.append(block)
        self.pending_blocks = still_pending

    def _on_block_finished(self, sm_id: int, block: ThreadBlock) -> None:
        sm = self.sms[sm_id]
        duration = block.duration_on_sm(self.config)
        sm.retire(block, duration)

        kernel = block.kernel
        kernel.blocks_remaining -= 1
        if kernel.blocks_remaining == 0:
            kernel.end_time = self.clock
            print(f"[t={self.clock:.5f}] kernel '{kernel.name}' (id={kernel.kernel_id}) COMPLETE -- took {kernel.duration:.5f}s")
            self.completed_kernels.append(kernel)
            stream = self.streams[kernel.stream_id]
            stream.finish_active()
            self._try_start_next_kernel(kernel.stream_id)

        # An SM slot just freed up -- see if any pending block (from this or
        # any other kernel/stream) can now be admitted.
        self._admit_pending_blocks()


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    config = GPUHardwareConfig(
        num_sms=4,
        max_resident_warps_per_sm=8,
        total_flops_per_sec=1e12,
        total_memory_bandwidth=1e11,
        mfu=0.5,
        mbu=0.5,
    )

    print("=" * 70)
    print("Demo 1: one stream, two kernels -- must run strictly in order")
    print("=" * 70)
    gpu = GPUStreamSim(config)
    gpu.submit_kernel(stream_id=0, name="qkv_proj", num_blocks=6, warps_per_block=4, flops_per_block=2e9, bytes_per_block=1e7)
    gpu.submit_kernel(stream_id=0, name="attention", num_blocks=6, warps_per_block=4, flops_per_block=3e9, bytes_per_block=5e7)
    gpu.run_until_idle()
    print(gpu.summary())

    print()
    print("=" * 70)
    print("Demo 2: two INDEPENDENT streams submitted together -- their blocks")
    print("share the same SM pool concurrently instead of waiting on each other")
    print("=" * 70)
    gpu2 = GPUStreamSim(config)
    gpu2.submit_kernel(stream_id=0, name="batch_A_step", num_blocks=6, warps_per_block=4, flops_per_block=2e9, bytes_per_block=1e7)
    gpu2.submit_kernel(stream_id=1, name="batch_B_step", num_blocks=6, warps_per_block=4, flops_per_block=2e9, bytes_per_block=1e7)
    gpu2.run_until_idle()
    print(gpu2.summary())
