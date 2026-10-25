from magic_box.pipeline.streams import DropOldestQueue, spawn_context
from tests.helpers import drain_until, produce_ints


def test_drain_empty_returns_empty_list():
    assert DropOldestQueue(4).drain() == []


def test_overflow_drops_oldest():
    q = DropOldestQueue(3)
    for i in range(5):
        q.put(i)
    assert drain_until(q, 3) == [2, 3, 4]
    assert q.dropped == 2


def test_cross_process_order_preserved():
    ctx = spawn_context()
    q = DropOldestQueue(256, ctx)
    proc = ctx.Process(target=produce_ints, args=(q, 100))
    proc.start()
    proc.join(10)
    assert drain_until(q, 100) == list(range(100))


def test_parent_aware_stop_follows_event_and_parent():
    from magic_box.pipeline.streams import ParentAwareStop

    class Ev:
        flag = False

        def is_set(self):
            return self.flag

        def wait(self, t=None):
            return self.flag

    now = [0.0]
    parent = [True]
    checks = []

    def alive():
        checks.append(now[0])
        return parent[0]

    ev = Ev()
    s = ParentAwareStop(ev, alive, check_s=1.0, clock=lambda: now[0])
    assert not s.is_set() and not s.is_set()
    assert checks == [0.0]  # the parent is polled once per second, not per call
    now[0] = 1.1
    parent[0] = False
    assert s.is_set() and s.is_set()  # stays set once the parent is gone
    ev2 = Ev()
    ev2.flag = True
    assert ParentAwareStop(ev2, alive).is_set()


def test_cancel_join_lets_a_child_exit_with_unread_items():
    import time

    from magic_box.pipeline.streams import DropOldestQueue, spawn_context
    from tests.helpers import flood_queue_then_exit

    ctx = spawn_context()
    q = DropOldestQueue(1000, ctx)
    child = ctx.Process(target=flood_queue_then_exit, args=(q, True))
    child.start()
    start = time.monotonic()
    child.join(15)
    try:
        assert not child.is_alive() and child.exitcode == 0
        assert time.monotonic() - start < 15
    finally:
        if child.is_alive():
            child.kill()
