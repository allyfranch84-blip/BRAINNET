import time

class Telemetry:

    def __init__(self):
        self.start = time.perf_counter()

    def finish(self):
        return {
            "elapsed": time.perf_counter() - self.start
        }