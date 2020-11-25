import time as ttime
import subprocess
import pytest

from ._common import (
    patch_first_startup_file,
    patch_first_startup_file_undo,
    wait_for_condition,
    condition_manager_idle,
    condition_manager_paused,
    condition_environment_created,
    condition_environment_closed,
    condition_queue_processing_finished,
    get_reduced_state_info,
    get_queue_state,
    get_queue,
)

from ._common import re_manager, re_manager_pc_copy  # noqa: F401


def test_qserver_cli_and_manager(re_manager):  # noqa: F811
    """
    Long test runs a series of CLI commands.
    """
    assert wait_for_condition(
        time=3, condition=condition_manager_idle
    ), "Timeout while waiting for manager to initialize."

    # Clear queue
    assert subprocess.call(["qserver", "-c", "queue_clear"]) == 0

    # Request the list of allowed plans and devices (we don't check what is returned)
    assert subprocess.call(["qserver", "-c", "plans_allowed"], stdout=subprocess.DEVNULL) == 0
    assert subprocess.call(["qserver", "-c", "devices_allowed"], stdout=subprocess.DEVNULL) == 0

    # Add a number of plans
    plan_1 = "{'name':'count', 'args':[['det1', 'det2']]}"
    plan_2 = "{'name':'scan', 'args':[['det1', 'det2'], 'motor', -1, 1, 10]}"
    plan_3 = "{'name':'count', 'args':[['det1', 'det2']], 'kwargs':{'num':10, 'delay':1}}"
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan_1]) == 0
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan_2]) == 0
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan_3]) == 0

    n_plans, is_plan_running, _ = get_reduced_state_info()
    assert n_plans == 3, "Incorrect number of plans in the queue"
    assert not is_plan_running, "Plan is executed while it shouldn't"

    assert subprocess.call(["qserver", "-c", "queue_get"]) == 0
    assert subprocess.call(["qserver", "-c", "queue_plan_remove"]) == 0

    n_plans, is_plan_running, _ = get_reduced_state_info()
    assert n_plans == 2, "Incorrect number of plans in the queue"

    assert subprocess.call(["qserver", "-c", "environment_open"]) == 0
    assert wait_for_condition(
        time=3, condition=condition_environment_created
    ), "Timeout while waiting for environment to be created"

    assert subprocess.call(["qserver", "-c", "queue_start"]) == 0

    assert wait_for_condition(
        time=60, condition=condition_queue_processing_finished
    ), "Timeout while waiting for process to finish"

    # Smoke test for 'history_get' and 'history_clear'
    assert subprocess.call(["qserver", "-c", "history_get"]) == 0
    assert subprocess.call(["qserver", "-c", "history_clear"]) == 0

    # Queue is expected to be empty (processed). Load one more plan.
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan_3]) == 0

    n_plans, is_plan_running, _ = get_reduced_state_info()
    assert n_plans == 1, "Incorrect number of plans in the queue"

    assert subprocess.call(["qserver", "-c", "queue_start"]) == 0
    ttime.sleep(1)
    assert subprocess.call(["qserver", "-c", "re_pause", "-p", "immediate"]) == 0
    assert wait_for_condition(
        time=60, condition=condition_manager_paused
    ), "Timeout while waiting for manager to pause"

    assert subprocess.call(["qserver", "-c", "re_resume"]) == 0
    ttime.sleep(1)
    assert subprocess.call(["qserver", "-c", "re_pause", "-p", "deferred"]) == 0
    assert wait_for_condition(
        time=60, condition=condition_manager_paused
    ), "Timeout while waiting for manager to pause"

    assert subprocess.call(["qserver", "-c", "re_resume"]) == 0

    assert wait_for_condition(
        time=60, condition=condition_queue_processing_finished
    ), "Timeout while waiting for process to finish"

    subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan_1])
    subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan_1])

    n_plans, is_plan_running, _ = get_reduced_state_info()
    assert n_plans == 2, "Incorrect number of plans in the queue"

    assert subprocess.call(["qserver", "-c", "queue_start"]) == 0

    assert wait_for_condition(
        time=60, condition=condition_queue_processing_finished
    ), "Timeout while waiting for process to finish"

    # Test 'killing' the manager during running plan. Load long plan and two short ones.
    #   The tests checks if execution of the queue is continued uninterrupted after
    #   the manager restart
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan_3]) == 0
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan_3]) == 0
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan_3]) == 0
    n_plans, is_plan_running, _ = get_reduced_state_info()
    assert n_plans == 3, "Incorrect number of plans in the queue"

    assert subprocess.call(["qserver", "-c", "queue_start"]) == 0
    ttime.sleep(1)
    assert subprocess.call(["qserver", "-c", "manager_kill"]) != 0
    ttime.sleep(6)  # Don't request the condition to avoid timeout error TODO: wait for the server
    assert wait_for_condition(
        time=60, condition=condition_queue_processing_finished
    ), "Timeout while waiting for process to finish"

    assert subprocess.call(["qserver", "-c", "environment_close"]) == 0
    assert wait_for_condition(
        time=5, condition=condition_environment_closed
    ), "Timeout while waiting for environment to be closed"


def test_qserver_environment_close(re_manager):  # noqa: F811
    """
    Test for `environment_close` command
    """
    assert wait_for_condition(
        time=3, condition=condition_manager_idle
    ), "Timeout while waiting for manager to initialize."

    # Clear queue
    assert subprocess.call(["qserver", "-c", "queue_clear"]) == 0

    plan = "{'name':'count', 'args':[['det1', 'det2']], 'kwargs':{'num':5, 'delay':1}}"
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan]) == 0

    n_plans, is_plan_running, _ = get_reduced_state_info()
    assert n_plans == 1, "Incorrect number of plans in the queue"
    assert is_plan_running is False

    assert subprocess.call(["qserver", "-c", "environment_open"]) == 0
    assert wait_for_condition(
        time=3, condition=condition_environment_created
    ), "Timeout while waiting for environment to be opened"

    assert subprocess.call(["qserver", "-c", "queue_start"]) == 0
    ttime.sleep(2)
    n_plans, is_plan_running, _ = get_reduced_state_info()
    assert n_plans == 0, "Incorrect number of plans in the queue"
    assert is_plan_running is True

    # Call is expected to fail, because a plan is currently running
    assert subprocess.call(["qserver", "-c", "environment_close"]) != 0

    assert wait_for_condition(
        time=60, condition=condition_queue_processing_finished
    ), "Timeout while waiting for process to finish"

    n_plans, is_plan_running, n_history = get_reduced_state_info()
    assert n_plans == 0, "Incorrect number of plans in the queue"
    assert is_plan_running is False
    assert n_history == 1

    # Now we can close the environment because plan execution is complete
    assert subprocess.call(["qserver", "-c", "environment_close"]) == 0
    assert wait_for_condition(
        time=5, condition=condition_environment_closed
    ), "Timeout while waiting for environment to be closed"


def test_qserver_environment_destroy(re_manager):  # noqa: F811
    """
    Test for `environment_destroy` command
    """
    assert wait_for_condition(
        time=3, condition=condition_manager_idle
    ), "Timeout while waiting for manager to initialize."

    # Clear queue
    assert subprocess.call(["qserver", "-c", "queue_clear"]) == 0

    plan = "{'name':'count', 'args':[['det1', 'det2']], 'kwargs':{'num':5, 'delay':1}}"
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan]) == 0

    n_plans, is_plan_running, _ = get_reduced_state_info()
    assert n_plans == 1, "Incorrect number of plans in the queue"
    assert is_plan_running is False

    assert subprocess.call(["qserver", "-c", "environment_open"]) == 0
    assert wait_for_condition(
        time=3, condition=condition_environment_created
    ), "Timeout while waiting for environment to be opened"

    assert subprocess.call(["qserver", "-c", "queue_start"]) == 0
    ttime.sleep(2)
    n_plans, is_plan_running, _ = get_reduced_state_info()
    assert n_plans == 0, "Incorrect number of plans in the queue"
    assert is_plan_running is True

    assert subprocess.call(["qserver", "-c", "environment_destroy"]) == 0
    assert wait_for_condition(
        time=3, condition=condition_manager_idle
    ), "Timeout while waiting for environment to be destroyed."

    n_plans, is_plan_running, _ = get_reduced_state_info()
    assert n_plans == 1, "Incorrect number of plans in the queue"
    assert is_plan_running is False

    assert subprocess.call(["qserver", "-c", "environment_open"]) == 0
    assert wait_for_condition(
        time=3, condition=condition_environment_created
    ), "Timeout while waiting for environment to be opened"

    assert subprocess.call(["qserver", "-c", "queue_start"]) == 0
    ttime.sleep(2)
    n_plans, is_plan_running, _ = get_reduced_state_info()
    assert n_plans == 0, "Incorrect number of plans in the queue"
    assert is_plan_running is True

    assert wait_for_condition(
        time=60, condition=condition_queue_processing_finished
    ), "Timeout while waiting for process to finish"

    n_plans, is_plan_running, n_history = get_reduced_state_info()
    assert n_plans == 0, "Incorrect number of plans in the queue"
    assert is_plan_running is False
    assert n_history == 2

    assert subprocess.call(["qserver", "-c", "environment_close"]) == 0
    assert wait_for_condition(
        time=5, condition=condition_environment_closed
    ), "Timeout while waiting for environment to be closed"


# fmt: off
@pytest.mark.parametrize("option_pause, option_continue", [
    ("deferred", "resume"),
    ("immediate", "resume"),
    ("deferred", "stop"),
    ("deferred", "abort"),
    ("deferred", "halt")
])
# fmt: on
def test_qserver_re_pause_continue(re_manager, option_pause, option_continue):  # noqa: F811
    """
    Test for `re_pause`, `re_resume`, `re_stop`, `re_abort` and `re_halt` commands
    """
    re_continue = f"re_{option_continue}"

    assert wait_for_condition(
        time=3, condition=condition_manager_idle
    ), "Timeout while waiting for manager to initialize."

    # Out of place calls
    assert subprocess.call(["qserver", "-c", re_continue]) != 0
    assert subprocess.call(["qserver", "-c", "re_pause", "-p", option_pause]) != 0

    # Clear queue
    assert subprocess.call(["qserver", "-c", "queue_clear"]) == 0

    plan = "{'name':'count', 'args':[['det1', 'det2']], 'kwargs':{'num': 10, 'delay': 1}}"
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan]) == 0
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan]) == 0

    n_plans, is_plan_running, _ = get_reduced_state_info()
    assert n_plans == 2, "Incorrect number of plans in the queue"
    assert is_plan_running is False

    assert subprocess.call(["qserver", "-c", "environment_open"]) == 0
    assert wait_for_condition(
        time=3, condition=condition_environment_created
    ), "Timeout while waiting for environment to be opened"

    assert subprocess.call(["qserver", "-c", "queue_start"]) == 0
    ttime.sleep(2)

    # Out of place calls
    assert subprocess.call(["qserver", "-c", re_continue]) != 0

    assert subprocess.call(["qserver", "-c", "re_pause", "-p", option_pause]) == 0
    assert wait_for_condition(
        time=3, condition=condition_manager_paused
    ), "Timeout while waiting for manager to pause"

    status = get_queue_state()
    assert status["manager_state"] == "paused"

    n_plans, is_plan_running, n_history = get_reduced_state_info()
    assert n_plans == 1, "Incorrect number of plans in the queue"
    assert is_plan_running is False
    assert n_history == 0

    # Out of place call
    assert subprocess.call(["qserver", "-c", "re_pause", "-p", option_pause]) != 0

    assert subprocess.call(["qserver", "-c", re_continue]) == 0

    if option_continue == "resume":
        n_history_expected = 2
    else:
        assert wait_for_condition(time=3, condition=condition_manager_idle)

        n_plans, is_plan_running, n_history = get_reduced_state_info()
        assert n_plans == 2, "Incorrect number of plans in the queue"
        assert is_plan_running is False
        assert n_history == 1

        assert subprocess.call(["qserver", "-c", "queue_start"]) == 0

        n_history_expected = 3  # Includes entry related to 1 stopped plan

    ttime.sleep(1)

    n_plans, is_plan_running, n_history = get_reduced_state_info()
    assert n_plans == 1, "Incorrect number of plans in the queue"
    assert is_plan_running is True
    assert n_history == n_history_expected - 2

    assert wait_for_condition(
        time=60, condition=condition_queue_processing_finished
    ), "Timeout while waiting for process to finish"

    n_plans, is_plan_running, n_history = get_reduced_state_info()
    assert n_plans == 0, "Incorrect number of plans in the queue"
    assert is_plan_running is False
    assert n_history == n_history_expected

    assert subprocess.call(["qserver", "-c", "environment_close"]) == 0
    assert wait_for_condition(
        time=5, condition=condition_environment_closed
    ), "Timeout while waiting for environment to be closed"


# fmt: off
@pytest.mark.parametrize("time_kill", ["before", 2, 8, "paused"])
# fmt: on
def test_qserver_manager_kill(re_manager, time_kill):  # noqa: F811
    """
    Test for `test_manager_kill` command. The command is stopping the event loop of RE Manager,
    causeing RE Watchdog to restart it. RE Manager can be restarted at any time: the restart
    should not affect executed plans or the state of the queue or RE Worker. Response to this
    command is never returned, so it can also be used to test how the system handles communication
    timeouts. It takes 5 seconds of RE Manager inactivity befor it is restarted. The following cases
    are tested:
    - RE Manager is killed and restarted before queue processing is started.
    - RE Manager is killed and restarted while the 1st plan in the queue is executed.
    - RE Manager is killed while the 1st plan is still executed and is not restarted before
    the plan execution is finished. RE Manager is supposed to recognize that the plan is completed,
    process the report and start processing of the next plan.
    - RE Manager is killed and restarted while the 1st plan is in 'paused' state. RE Manager is
    supposed to switch to 'paused' state at the restart. The plan can execution can be resumed.
    """
    assert wait_for_condition(
        time=3, condition=condition_manager_idle
    ), "Timeout while waiting for manager to initialize."

    # Clear queue
    assert subprocess.call(["qserver", "-c", "queue_clear"]) == 0

    plan = "{'name':'count', 'args':[['det1', 'det2']], 'kwargs':{'num': 10, 'delay': 1}}"
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan]) == 0
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan]) == 0

    assert subprocess.call(["qserver", "-c", "environment_open"]) == 0
    assert wait_for_condition(
        time=3, condition=condition_environment_created
    ), "Timeout while waiting for environment to be opened"

    if time_kill == "before":
        # The command that kills manager always times out
        assert subprocess.call(["qserver", "-c", "manager_kill"]) != 0
        ttime.sleep(8)  # It takes 5 seconds before the manager is restarted

        status = get_queue_state()
        assert status["manager_state"] == "idle"

    # Start queue processing
    assert subprocess.call(["qserver", "-c", "queue_start"]) == 0

    if isinstance(time_kill, int):
        ttime.sleep(time_kill)
        # The command that kills manager always times out
        assert subprocess.call(["qserver", "-c", "manager_kill"]) != 0
        ttime.sleep(8)  # It takes 5 seconds before the manager is restarted

        status = get_queue_state()
        assert status["manager_state"] == "executing_queue"

    elif time_kill == "paused":
        ttime.sleep(3)
        assert subprocess.call(["qserver", "-c", "re_pause", "-p", "deferred"]) == 0
        assert wait_for_condition(time=3, condition=condition_manager_paused)
        assert subprocess.call(["qserver", "-c", "manager_kill"]) != 0
        ttime.sleep(8)  # It takes 5 seconds before the manager is restarted

        status = get_queue_state()
        assert status["manager_state"] == "paused"

        assert subprocess.call(["qserver", "-c", "re_resume"]) == 0

    assert wait_for_condition(
        time=60, condition=condition_queue_processing_finished
    ), "Timeout while waiting for process to finish"

    n_plans, is_plan_running, n_history = get_reduced_state_info()
    assert n_plans == 0, "Incorrect number of plans in the queue"
    assert is_plan_running is False
    assert n_history == 2

    assert subprocess.call(["qserver", "-c", "environment_close"]) == 0
    assert wait_for_condition(
        time=5, condition=condition_environment_closed
    ), "Timeout while waiting for environment to be closed"


# fmt: off
@pytest.mark.parametrize("additional_code, success", [
    # Nothing is added. Load profiles as usual.
    ("""
""", True),

    # Simulate profile that takes long time to load.
    ("""
\n
import time as ttime
ttime.sleep(20)

""", True),

    # Raise exception while loading the profile. This should cause RE Worker to exit.
    ("""
\n
raise Exception("This exception is raised to test if error handling works correctly")

""", False),
])
# fmt: on
def test_qserver_env_open_various_cases(re_manager_pc_copy, additional_code, success):  # noqa: F811

    _, pc_path = re_manager_pc_copy

    # Patch one of the startup files.
    patch_first_startup_file(pc_path, additional_code)

    # Wait until RE Manager is started
    assert wait_for_condition(time=10, condition=condition_manager_idle)

    # Attempt to create the environment
    assert subprocess.call(["qserver", "-c", "environment_open"]) == 0
    assert wait_for_condition(time=30, condition=condition_manager_idle)

    status = get_queue_state()
    assert status["worker_environment_exists"] == success

    if not success:
        # Remove the offending patch and try to start the environment again. It should work
        patch_first_startup_file_undo(pc_path)
        assert subprocess.call(["qserver", "-c", "environment_open"]) == 0
        assert wait_for_condition(time=3, condition=condition_environment_created)

    # Run a plan to make sure RE Manager is functional after the startup.
    plan = "{'name':'count', 'args':[['det1', 'det2']], 'kwargs':{'num': 10, 'delay': 1}}"
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan]) == 0

    # Start queue processing
    assert subprocess.call(["qserver", "-c", "queue_start"]) == 0
    ttime.sleep(2)
    status = get_queue_state()
    assert status["manager_state"] == "executing_queue"

    assert wait_for_condition(time=60, condition=condition_queue_processing_finished)
    n_plans, is_plan_running, n_history = get_reduced_state_info()
    assert n_plans == 0, "Incorrect number of plans in the queue"
    assert is_plan_running is False
    assert n_history == 1

    assert subprocess.call(["qserver", "-c", "environment_close"]) == 0
    assert wait_for_condition(time=5, condition=condition_environment_closed)


# fmt: off
@pytest.mark.parametrize("option", [None, "safe_on", "safe_off"])
# fmt: on
def test_qserver_manager_stop_1(re_manager, option):  # noqa: F811
    """
    Method ``manager_stop``. Environment is in 'idle' state.
    """
    # Wait until RE Manager is started
    assert wait_for_condition(time=10, condition=condition_manager_idle)

    # Attempt to create the environment
    assert subprocess.call(["qserver", "-c", "environment_open"]) == 0
    assert wait_for_condition(time=30, condition=condition_manager_idle)

    cmd = ["qserver", "-c", "manager_stop"]
    if option:
        cmd += ["-p", option]

    assert subprocess.call(cmd) == 0

    # Check if RE Manager was stopped.
    assert re_manager.check_if_stopped() is True


# fmt: off
@pytest.mark.parametrize("option", [None, "safe_on", "safe_off"])
# fmt: on
def test_qserver_manager_stop_2(re_manager, option):  # noqa: F811
    """
    Method ``manager_stop``. Environment is running a plan.
    """
    # Wait until RE Manager is started
    assert wait_for_condition(time=10, condition=condition_manager_idle)

    # Attempt to create the environment
    assert subprocess.call(["qserver", "-c", "environment_open"]) == 0
    assert wait_for_condition(time=30, condition=condition_manager_idle)

    plan = "{'name':'count', 'args':[['det1', 'det2']], 'kwargs':{'num': 10, 'delay': 1}}"
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan]) == 0
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan]) == 0

    assert subprocess.call(["qserver", "-c", "queue_start"]) == 0
    ttime.sleep(2)
    status = get_queue_state()
    assert status["manager_state"] == "executing_queue"

    cmd = ["qserver", "-c", "manager_stop"]
    if option:
        cmd += ["-p", option]

    if option == "safe_off":
        assert subprocess.call(cmd) == 0

        # Check if RE Manager was stopped.
        assert re_manager.check_if_stopped() is True

    else:
        assert subprocess.call(cmd) != 0

        assert wait_for_condition(time=60, condition=condition_queue_processing_finished)
        n_plans, is_plan_running, n_history = get_reduced_state_info()
        assert n_plans == 0, "Incorrect number of plans in the queue"
        assert is_plan_running is False
        assert n_history == 2


# fmt: off
@pytest.mark.parametrize("pos, pos_result, success", [
    (None, 2, True),
    ("back", 2, True),
    ("front", 0, True),
    ("some", None, False),
    (0, 0, True),
    (1, 1, True),
    (2, 2, True),
    (3, 2, True),
    (100, 2, True),
    (-1, 1, True),
    (-2, 0, True),
    (-3, 0, True),
    (-100, 0, True),
])
# fmt: on
def test_queue_item_add_1(re_manager, pos, pos_result, success):  # noqa F811

    # Wait until RE Manager is started
    assert wait_for_condition(time=10, condition=condition_manager_idle)

    plan1 = "{'name':'count', 'args':[['det1']]}"
    plan2 = "{'name':'count', 'args':[['det1', 'det2']]}"

    # Create the queue with 2 entries
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan1]) == 0
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan1]) == 0

    # Add another entry at the specified position
    params = [plan2]
    if pos is not None:
        params.insert(0, str(pos))

    res = subprocess.call(["qserver", "-c", "queue_item_add", "-p", *params])
    if success:
        assert res == 0
    else:
        assert res != 0

    resp = get_queue()
    assert len(resp["queue"]) == (3 if success else 2)

    if success:
        assert resp["queue"][pos_result]["args"] == [["det1", "det2"]]
        assert "plan_uid" in resp["queue"][pos_result]


def test_queue_item_add_2(re_manager):  # noqa F811
    """
    Failing cases: adding the plans that are expected to fail validation.
    """
    # Wait until RE Manager is started
    assert wait_for_condition(time=10, condition=condition_manager_idle)

    # Unknown plan name
    plan1 = "{'name':'count_test', 'args':[['det1']]}"
    # Unknown kwarg
    plan2 = "{'name':'count', 'args':[['det1', 'det2']], 'kwargs':{'abc': 10}}"

    # Both calls are expected to fail
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan1]) != 0
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan2]) != 0


# fmt: off
@pytest.mark.parametrize("before, target_pos, result_order", [
    (True, 0, [2, 0, 1]),
    (False, 0, [0, 2, 1]),
    (True, 1, [0, 2, 1]),
    (False, 1, [0, 1, 2]),
])
# fmt: on
def test_queue_item_add_3(re_manager, before, target_pos, result_order):  # noqa F811
    """
    Insert an item before or after the element with a given UID
    """
    # Wait until RE Manager is started
    assert wait_for_condition(time=10, condition=condition_manager_idle)

    plan1 = "{'name':'count', 'args':[['det1']]}"
    plan2 = "{'name':'count', 'args':[['det1', 'det2']]}"
    plan3 = "{'name':'count', 'args':[['det2']]}"

    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan1]) == 0
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan2]) == 0

    # Read queue.
    queue_1 = get_queue()["queue"]
    assert len(queue_1) == 2
    uids_1 = [_["plan_uid"] for _ in queue_1]

    params = ["before_uid" if before else "after_uid", uids_1[target_pos], plan3]
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", *params]) == 0

    # Check if the element was inserted in the right plance
    queue_2 = get_queue()["queue"]
    assert len(queue_2) == 3
    uids_2 = [_["plan_uid"] for _ in queue_2]
    for n, uid in enumerate(uids_2):
        n_res = result_order[n]
        if (n_res < 2) and (uid != uids_1[n_res]):
            assert False, f"uids_1: {uids_1}, uids_2: {uids_2}, result_order: {result_order}"


# fmt: off
@pytest.mark.parametrize("pos", [None, "back"])
# fmt: on
def test_queue_item_add_4_fail(re_manager, pos):  # noqa F811
    """
    No plan is supplied.
    """
    # Wait until RE Manager is started
    assert wait_for_condition(time=10, condition=condition_manager_idle)

    if pos:
        assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", pos]) != 0
    else:
        assert subprocess.call(["qserver", "-c", "queue_item_add"]) != 0


# fmt: off
@pytest.mark.parametrize("pos", [10, "front", "back"])
# fmt: on
def test_queue_item_add_5_fail(re_manager, pos):  # noqa F811
    """
    Incorrect order of arguments (position is specified).
    """
    # Wait until RE Manager is started
    assert wait_for_condition(time=10, condition=condition_manager_idle)

    pos, plan = 10, "{'name':'count', 'args':[['det1']]}"
    params = [plan, str(pos)]
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", *params]) != 0


# fmt: off
@pytest.mark.parametrize("params, exit_code", [
    # Error while processing message by the manager
    (["before_uid", "some_uid", "plan"], 2),
    # Unknown keyword
    (["unknown_keyword", "some_uid", "plan"], 4),
    # Incorrect order of arguments
    (["plan", "before_uid", "some_uid"], 4),
    (["some_uid", "before_uid", "plan"], 4),
    (["some_uid", "plan", "before_uid"], 4),
])
# fmt: on
def test_queue_item_add_6_fail(re_manager, params, exit_code):  # noqa F811
    """
    Incorrect order of arguments (position is specified).
    """
    # Wait until RE Manager is started
    assert wait_for_condition(time=10, condition=condition_manager_idle)

    plan = "{'name':'count', 'args':[['det1']]}"
    params = [_ if _ != "plan" else plan for _ in params]
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", *params]) == exit_code


# fmt: off
@pytest.mark.parametrize("pos, uid_ind, pos_result, success", [
    (None, None, 2, True),
    ("back", None, 2, True),
    ("front", None, 0, True),
    ("some", None, None, False),
    (0, None, 0, True),
    (1, None, 1, True),
    (2, None, 2, True),
    (3, None, None, False),
    (100, None, None, False),
    (-1, None, 2, True),
    (-2, None, 1, True),
    (-3, None, 0, True),
    (-4, None,  0, False),
    (-100, None, 0, False),
    (None, 0, 0, True),
    (None, 1, 1, True),
    (None, 2, 2, True),
    (None, 3, 2, False),
])
# fmt: on
def test_queue_item_get_remove(re_manager, pos, uid_ind, pos_result, success):  # noqa F811
    """
    Tests for ``queue_item_get`` and ``queue_plan_remove`` requests.
    """
    plans = [
        "{'name':'count', 'args':[['det1']]}",
        "{'name':'count', 'args':[['det2']]}",
        "{'name':'count', 'args':[['det1', 'det2']]}",
    ]
    plans_args = [[["det1"]], [["det2"]], [["det1", "det2"]]]

    for plan in plans:
        assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan]) == 0

    queue_1 = get_queue()["queue"]
    assert len(queue_1) == 3
    uids_1 = [_["plan_uid"] for _ in queue_1]
    uids_1.append("unknown_uid")  # Extra element (for one of the tests)

    if uid_ind is None:
        # Remove entry at the specified position
        args = ["-p", str(pos)] if (pos is not None) else []
    else:
        uid = uids_1[uid_ind]
        args = ["-p", uid]

    # Testing 'queue_item_get'. ONLY THE RETURN CODE IS TESTED.
    res = subprocess.call(["qserver", "-c", "queue_item_get", *args])
    if success:
        assert res == 0
    else:
        assert res != 0

    # Testing 'queue_plan_remove'.
    res = subprocess.call(["qserver", "-c", "queue_plan_remove", *args])
    if success:
        assert res == 0
    else:
        assert res != 0

    queue_2 = get_queue()["queue"]
    assert len(queue_2) == (2 if success else 3)
    if success:
        ind = [0, 1, 2]
        ind.pop(pos_result)
        # Check that the right entry disappeared from the queue.
        assert queue_2[0]["args"] == plans_args[ind[0]]
        assert queue_2[1]["args"] == plans_args[ind[1]]


# fmt: off
@pytest.mark.parametrize("params, result_order, exit_code", [
    # 'params': positions are always represented as str, all int's are UIDs.
    (["0", "1"], [1, 0, 2], 0),
    (["2", "0"], [2, 0, 1], 0),
    (["2", "-3"], [2, 0, 1], 0),
    (["-1", "-3"], [2, 0, 1], 0),
    (["2", "-5"], [0, 1, 2], 2),  # Destination index out of range
    (["1", "3"], [0, 1, 2], 2),  # Destination index out of range
    (["front", "back"], [1, 2, 0], 0),
    (["back", "front"], [2, 0, 1], 0),
    ([1, "before", 0], [1, 0, 2], 0),
    ([0, "after", 1], [1, 0, 2], 0),
    (["1", "before", 0], [1, 0, 2], 0),  # Mixed pos->uid
    (["0", "after", 1], [1, 0, 2], 0),  # Mixed pos->uid
    ([1, "0"], [1, 0, 2], 0),  # Mixed uid->pos
    ([1, "2"], [0, 2, 1], 0),  # Mixed uid->pos
    (["1", "unknown_kwd", 0], [0, 1, 2], 4),  # Mixed pos->uid
    (["0", "after"], [0, 1, 2], 2),  # Second parameter is considered as UID
    (["0"], [0, 1, 2], 4),  # Not enough parameters

])
# fmt: on
def test_queue_item_get_move(re_manager, params, result_order, exit_code):  # noqa F811
    """
    Tests for ``queue_item_get`` and ``queue_plan_remove`` requests.
    """
    plans = [
        "{'name':'count', 'args':[['det1']]}",
        "{'name':'count', 'args':[['det2']]}",
        "{'name':'count', 'args':[['det1', 'det2']]}",
    ]

    for plan in plans:
        assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan]) == 0

    queue_1 = get_queue()["queue"]
    assert len(queue_1) == 3
    uids_1 = [_["plan_uid"] for _ in queue_1]
    uids_1.append("unknown_uid")  # Extra element (for one of the tests)

    # Replace ints with UIDs (positions are represented as strings)
    params = params.copy()
    for n, p in enumerate(params):
        if isinstance(p, int):
            params[n] = uids_1[p]

    # Testing 'queue_item_get'. ONLY THE RETURN CODE IS TESTED.
    assert subprocess.call(["qserver", "-c", "queue_plan_move", "-p", *params]) == exit_code

    queue_2 = get_queue()["queue"]
    assert len(queue_2) == 3
    uids_2 = [_["plan_uid"] for _ in queue_2]

    # Compare the order of UIDs before and after moving the element
    uids_1_reordered = [uids_1[_] for _ in result_order]
    assert uids_1_reordered == uids_2


# fmt: off
@pytest.mark.parametrize("deactivate", [False, True])
# fmt: on
def test_qserver_queue_stop(re_manager, deactivate):  # noqa: F811
    """
    Methods ``queue_stop`` and ``queue_stop_cancel``.
    """
    # Wait until RE Manager is started
    assert wait_for_condition(time=10, condition=condition_manager_idle)

    # Attempt to create the environment
    assert subprocess.call(["qserver", "-c", "environment_open"]) == 0
    assert wait_for_condition(time=10, condition=condition_manager_idle)

    plan = "{'name':'count', 'args':[['det1', 'det2']], 'kwargs':{'num': 10, 'delay': 1}}"
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan]) == 0
    assert subprocess.call(["qserver", "-c", "queue_item_add", "-p", plan]) == 0

    # Queue is not running, so the request is expected to fail
    assert subprocess.call(["qserver", "-c", "queue_stop"]) != 0
    status = get_queue_state()
    assert status["queue_stop_pending"] is False

    assert subprocess.call(["qserver", "-c", "queue_start"]) == 0
    ttime.sleep(2)
    status = get_queue_state()
    assert status["manager_state"] == "executing_queue"

    assert subprocess.call(["qserver", "-c", "queue_stop"]) == 0
    status = get_queue_state()
    assert status["queue_stop_pending"] is True

    if deactivate:
        ttime.sleep(1)
        assert subprocess.call(["qserver", "-c", "queue_stop_cancel"]) == 0
        status = get_queue_state()
        assert status["queue_stop_pending"] is False

    assert wait_for_condition(time=60, condition=condition_manager_idle)
    n_plans, is_plan_running, n_history = get_reduced_state_info()
    assert n_plans == (0 if deactivate else 1)
    assert is_plan_running is False
    assert n_history == (2 if deactivate else 1)
    status = get_queue_state()
    assert status["queue_stop_pending"] is False
