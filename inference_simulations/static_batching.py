import threading
import queue
import time
import random
from typing import Callable
from inference_request import InferenceRequest



def submit_batch_on_gpu(request_batch: list[InferenceRequest], batch_id: int):
	""" Simulation of scheduling any request to GPU"""
	for request in request_batch:
		print(f"batch_id:{batch_id}: {request}")


class StaticBatchProcessWorkPool:
	"""Threadworkders for Task
	This is static batch pool which read batch_size request from queue and execute it as one batch
	If Number of request are less than batch_size it will execute on partial batch 
	"""
	def __init__(self, number_of_workers: int, task: Callable[[queue.Queue], None], q: queue.Queue, max_batch_wait_time_in_sec: int, batch_size: int):
		self.threadPool = []
		for index in range(0,number_of_workers):
			self.threadPool.append(threading.Thread(target=task, args=(q,index,max_batch_wait_time_in_sec,batch_size,)))
			self.threadPool[-1].start()

	def join_all(self):
		for t in self.threadPool:
			t.join()
		self.joined = True

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.join_all()
		return False


class RequestProcessingService:
	def __init__(self, number_of_workers: int, q: queue.Queue):
		self.number_of_workers = number_of_workers
		self.q = q
		self.request_id = 0

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		for _ in range(0, self.number_of_workers):
			self.q.put(None)

	def submit_request(self, prompt: str):
		""" Submit a request for inference """
		self.q.put(InferenceRequest(prompt, self.request_id))
		self.request_id = self.request_id + 1
		time.sleep(random.uniform(0.01, 0.03))



def gather_requests(q: queue.Queue, max_batch_wait_time_in_sec: int, batch_size: int) -> [list[InferenceRequest], bool]:
	""" Gather batch of requests
	return if accumulated batch and sentinel
	We would process partial batches if timeout is reached
	"""
	deadline = time.monotonic() + max_batch_wait_time_in_sec
	request_batch = []
	sentinel = False
	try:
		for _ in range(0, batch_size):
			remaining = deadline - time.monotonic()
			if remaining <=0:
				break
			item = q.get(timeout=remaining)
			if item is None:
				sentinel = True
				break
			request_batch.append(item)
	except queue.Empty:
		pass
	return request_batch, sentinel




def batch_schedule(q: queue.Queue, worker_index: int, max_batch_wait_time_in_sec: int, batch_size: int):
	""" Schedules a particular batch
	Policy is it will wait for max_batch_wait_time_in_sec if no more request comes it will execute partial batch
	We will still Use None as SENTINEL
	"""
	print(f"Starting batch schedule index: {worker_index}")
	processed_batch_index = 0
	while True:
		try:
			request_batch, sentinel = gather_requests(q, max_batch_wait_time_in_sec, batch_size)
			if len(request_batch) > 0:
				batch_id = str(worker_index) + "###" + str(processed_batch_index)
				processed_batch_index = processed_batch_index + 1
				submit_batch_on_gpu(request_batch, batch_id)
			if sentinel == True:
				break
		except ValueError as e:
			break



def main():
	number_of_workers = 3
	q = queue.Queue(maxsize=(5+number_of_workers))
	max_batch_wait_time_in_sec = 5
	batch_size = 2

	### Start Listening to request
	def run_work_pool():
		with StaticBatchProcessWorkPool(number_of_workers, batch_schedule, q, max_batch_wait_time_in_sec, batch_size) as cWP:
			pass
	lP = threading.Thread(target=run_work_pool)
	lP.start()

	### Start Submitting Request
	with RequestProcessingService(number_of_workers, q) as rPS:
		rPS.submit_request("Tell me weather of san francisco")
		rPS.submit_request("How is your day going??")
		rPS.submit_request("What is most fun thing to do??")
		rPS.submit_request("Do you know mood today?")

	lP.join()


if __name__ == "__main__":
	main()