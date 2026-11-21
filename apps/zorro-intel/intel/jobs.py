"""The worker threads of one window. Work runs in a thread; its result is handed to `post`
(the window gives GLib.idle_add), so widgets are only touched on the main loop."""
import threading
import time


class Jobs:
    def __init__(self, post):
        self.post = post
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.running = {}                   # thread -> cancel function or None

    def run(self, work, done=None, cancel=None):
        """work() in a thread, then done(result) through post. cancel() is called if the window closes first."""
        if self.closed.is_set():
            return None

        def body():
            try:
                result = work()
            finally:
                with self.lock:
                    self.running.pop(threading.current_thread(), None)
            if done and not self.closed.is_set():
                self.post(done, result)

        thread = threading.Thread(target=body, daemon=True)
        with self.lock:
            self.running[thread] = cancel
        thread.start()
        return thread

    def later(self, fn, *args):
        """from a worker: call fn(*args) on the main loop, unless the window is gone"""
        if not self.closed.is_set():
            self.post(fn, *args)

    def close(self, wait=3.0):
        """The window closes: cancel what can be cancelled and give the threads `wait` seconds to end."""
        self.closed.set()
        with self.lock:
            running = dict(self.running)
        for cancel in running.values():
            if cancel:
                cancel()
        deadline = time.monotonic() + wait
        for thread in running:
            thread.join(max(0.0, deadline - time.monotonic()))
