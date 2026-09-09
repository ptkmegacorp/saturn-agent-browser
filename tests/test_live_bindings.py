"""Live document generation tests."""

from __future__ import annotations

import unittest

from saturn_fbc.browser.live_bindings import attach_live_bindings, bump_document, read_live_bindings


class FakeFrame:
    def __init__(self, *, main: bool):
        self.parent_frame = None if main else object()


class FakePage:
    def __init__(self, url: str = "https://example.com/login"):
        self.url = url
        self.context = FakeContext()
        self._handlers: dict[str, list] = {}

    def on(self, event, handler):
        self._handlers.setdefault(event, []).append(handler)


class FakeContext:
    pass


class LiveBindingTests(unittest.TestCase):
    def test_attach_assigns_stable_tab_and_session(self) -> None:
        page = FakePage()
        attach_live_bindings(page)
        session, tab, doc = read_live_bindings(page)
        self.assertTrue(session.startswith("browser-"))
        self.assertTrue(tab.startswith("tab-"))
        self.assertTrue(doc.startswith("doc-"))
        again = read_live_bindings(page)
        self.assertEqual(again[0], session)
        self.assertEqual(again[1], tab)
        self.assertEqual(again[2], doc)

    def test_same_origin_navigation_bumps_document_only(self) -> None:
        page = FakePage()
        attach_live_bindings(page)
        session, tab, doc = read_live_bindings(page)
        for handler in page._handlers["framenavigated"]:
            handler(FakeFrame(main=True))
        session2, tab2, doc2 = read_live_bindings(page)
        self.assertEqual(session2, session)
        self.assertEqual(tab2, tab)
        self.assertNotEqual(doc2, doc)
        self.assertIn("-navigate-", doc2)

    def test_crash_bumps_document(self) -> None:
        page = FakePage()
        attach_live_bindings(page)
        before = read_live_bindings(page)[2]
        for handler in page._handlers["crash"]:
            handler(page)
        after = read_live_bindings(page)[2]
        self.assertNotEqual(after, before)
        self.assertIn("-crash-", after)

    def test_subframe_navigation_does_not_bump(self) -> None:
        page = FakePage()
        attach_live_bindings(page)
        before = read_live_bindings(page)[2]
        for handler in page._handlers["framenavigated"]:
            handler(FakeFrame(main=False))
        self.assertEqual(read_live_bindings(page)[2], before)

    def test_bump_helper(self) -> None:
        page = FakePage()
        first = bump_document(page, reason="attach")
        second = bump_document(page, reason="navigate")
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
