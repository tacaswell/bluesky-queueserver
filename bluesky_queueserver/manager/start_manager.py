from multiprocessing import Pipe
import threading
import time as ttime

from .worker import RunEngineWorker
from .manager import RunEngineManager
from .comms import PipeJsonRpcReceive

import logging
logger = logging.getLogger(__name__)


class WatchdogProcess:
    def __init__(self):
        self._re_manager = None
        self._re_worker = None

        # Create pipes used for connections of the modules
        self._manager_conn = None  # Worker -> Manager
        self._worker_conn = None  # Manager -> Worker
        self._watchdog_to_manager_conn = None  # Watchdog -> Manager
        self._manager_to_watchdog_conn = None  # Manager -> Watchdog
        self._create_conn_pipes()

        # Class that supports communication over the pipe
        self._comm_to_manager = PipeJsonRpcReceive(conn=self._watchdog_to_manager_conn)

        self._watchdog_state = 0  # State is currently just time since last notification
        self._watchdog_state_lock = threading.Lock()

        self._manager_is_stopping = False  # Set True to stop the server

    def _create_conn_pipes(self):
        # Manager to worker
        self._manager_conn, self._worker_conn = Pipe()
        # Watchdog to manager
        self._watchdog_to_manager_conn, self._manager_to_watchdog_conn = Pipe()

    # ======================================================================
    #             Handlers for messages from RE Manager

    def _start_re_worker_handler(self):
        """
        Creates worker process. This is a quick operation, because it starts RE Worker
        process without waiting for initialization.
        """
        logger.info("Starting RE Worker ...")
        try:
            self._re_worker = RunEngineWorker(conn=self._manager_conn, name="RE Worker Process")
            self._re_worker.start()
            success, err_msg = True, ""
        except Exception as ex:
            success, err_msg = False, str(ex)
        return {"success": success, "err_msg": err_msg}

    def _join_re_worker_handler(self, *, timeout=0.5):
        """
        Join RE Worker process after it was orderly closed by RE Manager. Watchdog module doesn't
        communicate with the worker process directly. This is responsibility of the RE Manager.
        But RE Manager doesn't hold reference to RE Worker, so it needs to be joined here.
        """
        logger.info("Joining RE Worker ...")
        self._re_worker.join(timeout)  # Try to join with timeout
        success = not self._re_worker.is_alive()  # Return success
        return {"success": success}

    def _kill_re_worker_handler(self):
        """
        Kill RE Worker by request from RE Manager. This is done only if RE Worker is non-responsive
        and can not be orderly stopped.
        """
        # TODO: kill() or terminate()???
        logger.info("Killing RE Worker ...")
        self._re_worker.kill()
        return {"success": True}

    def _is_worker_alive_handler(self):
        """
        Checks if RE Worker process is in running state. It doesn't mean that it is responsive.
        """
        is_alive = False
        if hasattr(self._re_worker, "is_alive"):
            is_alive = self._re_worker.is_alive()
        return {"worker_alive": is_alive}

    def _manager_stopping_handler(self):
        """
        Manager informed that it is stopping and should not be restarted.
        """
        self._manager_is_stopping = True

    def _init_watchdog_state(self):
        with self._watchdog_state_lock:
            self._watchdog_state = ttime.time()

    def _register_heartbeat_handler(self, *, value):
        """
        Heartbeat is received. Update the state.
        """
        if value == "alive":
            self._init_watchdog_state()

    # ======================================================================

    def _start_re_manager(self):
        self._init_watchdog_state()
        self._re_manager = RunEngineManager(conn_watchdog=self._manager_to_watchdog_conn,
                                            conn_worker=self._worker_conn,
                                            name="RE Manager Process")
        self._re_manager.start()

    def run(self):

        # Requests
        self._comm_to_manager.add_method(self._start_re_worker_handler, "start_re_worker")
        self._comm_to_manager.add_method(self._join_re_worker_handler, "join_re_worker")
        self._comm_to_manager.add_method(self._kill_re_worker_handler, "kill_re_worker")
        self._comm_to_manager.add_method(self._manager_stopping_handler, "manager_stopping")
        # Notifications
        self._comm_to_manager.add_method(self._is_worker_alive_handler, "is_worker_alive")
        self._comm_to_manager.add_method(self._register_heartbeat_handler, "heartbeat")

        self._comm_to_manager.start()

        self._start_re_manager()
        while True:
            # Primitive implementation of the loop that restarts the process.
            self._re_manager.join(0.1)  # Small timeout

            if self._manager_is_stopping and not self._re_manager.is_alive():
                break  # Exit if the program was actually stopped (process joined)

            with self._watchdog_state_lock:
                time_passed = ttime.time() - self._watchdog_state

            # Interval is used to protect the system from restarting in case of clock issues.
            # It may be a better idea to implement a ticker in a separate thread to act as
            #   a clock to be completely independent from system clock.
            if (time_passed > 5.0) and (time_passed < 15.0) and not self._manager_is_stopping:
                logger.error("Timeout detected by Watchdog. RE Manager malfunctioned and must be restarted.")
                self._re_manager.kill()
                self._start_re_manager()

        self._comm_to_manager.stop()


def start_manager():

    logging.basicConfig(level=logging.WARNING)
    logging.getLogger('bluesky_queueserver').setLevel("DEBUG")

    wp = WatchdogProcess()
    try:
        wp.run()
    except KeyboardInterrupt:
        logger.info("The program was manually stopped.")
