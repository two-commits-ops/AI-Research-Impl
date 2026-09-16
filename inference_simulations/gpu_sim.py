
import threading
import queue
import time
import random
from inference_request import InferenceRequest
from typing import Callable



## ************************************************************ ##
## ************************* GPU CONFIG ************************ ##
## ************************************************************ ##
class GPUConfig:
	def __init__(self, flops_per_sec: float, total_memory: float, memory_bandwidth: float, mfu: float, mbu: float, num_of_warps_per_sm: int,  number_of_sms: int):
		"""
		This is single GPU config with multiple SMs, any other latency is conidered approx 0
		"""
		self.flops_per_sec = flops_per_sec
		self.total_memory = total_memory
		self.memory_bandwidth = memory_bandwidth
		self.mfu = mfu
		self.mbu = mbu
		self.num_of_warps_per_sm = num_of_warps_per_sm
		self.number_of_sms = number_of_sms

	@classmethod
	def default(cls):
		return cls(1e9, 32*1e9, 12*10e8,0.65, 0.87, 4, 6)


	def __repr__(self):
		return f"{self.flops_per_sec=} {self.total_memory=} {self.memory_bandwidth=} {self.mfu=} {self.mbu=} {self.num_of_warps_per_sm=}  {self.number_of_sms=}"


## ************************************************************ ##
## ************************* GPU INFERENCE TASK ************************ ##
## ************************************************************ ##
class GPUInferenceTask:
	""" Simulate GPU level task, in reality this would be compiled graph which can be executed on GPU"""
	def __init__(self, task: Callable[[list[InferenceRequest]], None], task_data: list[InferenceRequest]):
		self.task = task
		self.task_data = task_data


## ************************************************************ ##
## ************************* GPU TASK POOL ************************ ##
## ************************************************************ ##
class GPUTaskPool:
	"""
	This simulates execution of tasks
	"""
	def __init__(self, pool_size: int, task_timeout_in_sec: float):
		self.pool_size = pool_size
		self.pool = []
		self.q: queue.Queue[GPUInferenceTask] = queue.Queue(maxsize=10)
		self.task_timeout_in_sec = task_timeout_in_sec

		def task_executor():
			""" Wait for task and execute it """
			while True:
				try:
					item: GPUInferenceTask = self.q.get(timeout=self.task_timeout_in_sec)
				except queue.Empty:
        			continue   # nothing arrived in time — loop back and wait again, don't exit
				if item is None:
					break
				item.task(item.task_data)

			except queue.Empty as e:
				pass

				

		for _ in range(0, self.pool_size):
			self.pool.append(threading.Thread(target=task_executor))
			self.pool[-1].start()

	def join_all(self):
		for _ in self.pool:
			self.q.put(None)

		for t in self.pool:
			t.join()

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.join_all()
		


	def submit_task(self, task: GPUInferenceTask):
		""" Submit a task run on Task pool """
		self.q.put(task)


## ************************************************************ ##
## ************************* GPU RUNNER ************************ ##
## ************************************************************ ##

class GPURunner:
	def __init__(self, pool_size: int):
		self.pool = GPUTaskPool(pool_size, 5)
		self.task_runners = []

	def join_all(self):
		for task_runner in self.task_runners:
			task_runner.join_all()
		self.pool.join_all()

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.join_all()


## ************************************************************ ##
## ************************* GPU WARP SIM ************************ ##
## ************************************************************ ##
class GPUWarpSim(GPURunner):
	""" Warp simulation of GPU SM"""
	def __init__(self, sm_id: int, warp_id: int, task_completion: Callable[[int], None]):
		self.sm_id = sm_id
		self.warp_id = warp_id
		super().__init__(32)
		self.task_completion = task_completion
		self.number_of_request_pending = 0


	def thread_task_execution(self, thread_task: list[InferenceRequest]):
		"""
		Here size of list is always 1
		"""
		assert len(thread_task) == 1
		### Just a simulation time
		time.sleep(random.uniform(0.01, 0.03))
		self.number_of_request_pending = self.number_of_request_pending - 1
		print(f" Completed Request: {thread_task[0]} {self.warp_id=} {self.sm_id=}")
		if self.number_of_request_pending == 0:
			self.task_completion(self.warp_id)


	def submit_batch(self, request_batch: list[InferenceRequest]):
		"""
		For simplicity let's assume within a request batch, each request can be executed over a warp thread
		so we will assign each request to a wap thread
		"""
		self.number_of_request_pending = len(request_batch)
		for request in request_batch:
			self.pool.submit_task(GPUInferenceTask(self.thread_task_execution, [request]))



## ************************************************************ ##
## ************************* GPU SM SIM ************************ ##
## ************************************************************ ##
class GPUSMSim(GPURunner):
	""" SM simulator of GPU"""
	def __init__(self, sm_id: int, number_of_warps: int, task_completion: Callable[[int], None]):
		self.sm_id = sm_id
		self.number_of_warps = number_of_warps
		super().__init__(number_of_warps)
		self.warp_available_index_q = queue.Queue()
		self.task_completion = task_completion

		def warp_task_completion(warp_index: int):
			self.warp_available_index_q.put(warp_index)
			if self.warp_available_index_q.qsize() == self.number_of_warps:
				## All waps within sm have completed execution
				self.task_completion(self.sm_id)

		for i in range(0, number_of_warps):
			self.warp_available_index_q.put(i)
			self.task_runners.append(GPUWarpSim(self.sm_id, i, warp_task_completion))



	def warp_task_execution(self, warp_task: list[InferenceRequest]):
		try:
			item = self.warp_available_index_q.get()
			if item is None:
				return

			self.task_runners[item].submit_batch(warp_task)
		except queue.Empty as e:
			pass

	def submit_batch(self, request_batch: list[InferenceRequest]):
		self.pool.submit_task(GPUInferenceTask(self.warp_task_execution, request_batch))



## ************************************************************ ##
## ************************* GPU SIM ************************ ##
## ************************************************************ ##
class GPUSim(GPURunner):
	def __init__(self, config: GPUConfig):
		self.config = config
		super().__init__(self.config.number_of_sms)
		self.sm_available_index_q = queue.Queue()
		def sm_task_completion(sm_index: int):
			self.sm_available_index_q.put(sm_index)

		for i in range(0, self.config.number_of_sms):
			self.sm_available_index_q.put(i)
			self.task_runners.append(GPUSMSim(i, self.config.num_of_warps_per_sm, sm_task_completion))


	def sm_task_execution(self, sm_task: list[InferenceRequest]):
		""" Pick up dedicated SM and execute task on SM
		"""
		try:
			item = self.sm_available_index_q.get()
			if item is None:
				return

			self.task_runners[item].submit_batch(sm_task)
		except queue.Empty as e:
			pass



	def submit_batch(self, request_batch: list[InferenceRequest]):
		self.pool.submit_task(GPUInferenceTask(self.sm_task_execution, request_batch))










