class InferenceRequest:
	""" Simulation of inference request
	This is is a very simple text based request

	"""
	def __init__(self, prompt: str, request_id: int):
		self.prompt = prompt
		self.request_id = request_id

	def __repr__(self):
		return f"{self.request_id=} : {self.prompt=}"