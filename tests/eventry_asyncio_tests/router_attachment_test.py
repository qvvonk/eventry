import pytest
from eventry.asyncio import Router
from eventry.asyncio.exceptions import router as rexc


class TestRouterAttachment:
    def test_cannot_attach_router_to_itself(self):
        r = Router()

        with pytest.raises(rexc.RouterLoopError):
            r.attach_router(r)

    def test_cannot_attach_router_with_a_parent(self):
        r0, r1, r2 = Router(), Router(), Router()
        r1.attach_router(r2)

        with pytest.raises(rexc.RouterAlreadyAttachedError):
            r0.attach_router(r2)

    def test_cannot_attach_to_ascendant_router(self):
        r0, r1, r2 = Router(), Router(), Router()
        r0.attach_router(r1)
        r1.attach_router(r2)

        with pytest.raises(rexc.RouterLoopError):
            r2.attach_router(r0)

    def test_cannot_attach_routers_with_eq_names(self):
        r0, r1, r2 = Router(name='parent'), Router(name='child'), Router(name='child')
        r0.attach_router(r1)

        with pytest.raises(rexc.DuplicateSubrouterNameError):
            r0.attach_router(r2)

    def test_router_attachment(self):
        r0, r1 = Router(name='parent'), Router(name='child')
        r0.attach_router(r1)

        assert 'child' in r0.sub_routers
        assert r1.parent is r0


class TestRouterDetachment:
    def test_router_detachment_from_parent(self):
        r0, r1 = Router(name='parent'), Router(name='child')
        r0.attach_router(r1)

        result = r0.detach_router('child')

        assert result is r1
        assert 'child' not in r0.sub_routers
        assert r1.parent is None

    def test_router_detachment_from_child(self):
        r0, r1 = Router(name='parent'), Router(name='child')
        r0.attach_router(r1)

        result = r1.detach()

        assert result is r1
        assert 'child' not in r0.sub_routers
        assert r1.parent is None

    def test_cannot_detach_non_existing_router(self):
        r0 = Router()

        with pytest.raises(KeyError):
            r0.detach_router('child')