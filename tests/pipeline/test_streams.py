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
