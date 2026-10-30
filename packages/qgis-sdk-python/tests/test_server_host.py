"""The server host without a server: hooks, ordering and the plain models.

Decision-52 fixes the hook shapes and the order they run in (decision-69 point
1); the fake ``QgsServerInterface`` in ``qgis_sdk.testing`` is what makes those
claims provable on a machine whose QGIS has no server bindings, which is every
environment this workspace can reach. Nothing here imports QGIS.
"""

from __future__ import annotations

import pytest
from qgis_sdk.core import Host, ResourceScope
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.models import QgisSdkUnsupportedCapabilityError
from qgis_sdk.server import (
    CaseInsensitiveMapping,
    HookDeclaration,
    ServerContext,
    ServerHooks,
    ServerHost,
    ServerRequest,
    ServerResponse,
    access_control,
    filter,
    service,
)
from qgis_sdk.testing import FakeServerInterface

#: The attribute the decorators write their metadata under.
HOOK_ATTRIBUTE = "__qgis_sdk_server_hook__"


def declaration_of(hook: object) -> HookDeclaration | None:
    """What a decorator recorded on ``hook``, if anything."""
    recorded = getattr(hook, HOOK_ATTRIBUTE)
    return recorded if isinstance(recorded, HookDeclaration) else None


def request(**params: str) -> ServerRequest:
    return ServerRequest(
        method="GET",
        url="http://localhost/qgis/qgis_mapserv.fcgi",
        params=params,
        headers={"Accept": "text/xml"},
    )


def capabilities() -> ServerRequest:
    return request(SERVICE="WMS", REQUEST="GetCapabilities", VERSION="1.3.0")


# -- the request model -------------------------------------------------------------


def test_ogc_parameters_are_read_whatever_their_case() -> None:
    served = request(service="WMS", LAYERS="parcels")

    assert served.param("SERVICE") == "WMS"
    assert served.param("Service") == "WMS"
    assert served.param("layers") == "parcels"
    assert served.param("BBOX") is None
    assert served.param("BBOX", "0,0,1,1") == "0,0,1,1"


def test_parameters_iterate_in_the_spelling_they_arrived_in() -> None:
    served = request(SERVICE="WMS", Layers="parcels")

    assert list(served.params) == ["SERVICE", "Layers"]
    # A rewrite replaces the value and keeps the spelling the caller sent, so a
    # request that echoes its parameters echoes what arrived, not what a filter
    # typed.
    rewritten = served.params.merged(LAYERS="roads")
    assert list(rewritten) == ["SERVICE", "Layers"]
    assert rewritten.get("layers") == "roads"


def test_headers_are_case_insensitive_too() -> None:
    served = request()

    assert served.header("accept") == "text/xml"
    assert served.header("Accept-Encoding", "identity") == "identity"


def test_rewriting_a_request_leaves_the_original_alone() -> None:
    original = request(SERVICE="WMS")

    rewritten = original.with_params(VERSION="1.3.0", SERVICE="WFS")

    assert original.param("VERSION") is None
    assert rewritten.param("version") == "1.3.0"
    assert rewritten.param("SERVICE") == "WFS"


def test_a_case_insensitive_mapping_explains_itself() -> None:
    assert repr(CaseInsensitiveMapping({"SERVICE": "WMS"})) == (
        "CaseInsensitiveMapping(SERVICE='WMS')"
    )


# -- the response model ------------------------------------------------------------


def test_a_response_starts_as_the_xml_answer_qgis_expects() -> None:
    response = ServerResponse()

    assert (response.status, response.header("content-type")) == (200, "text/xml")
    assert response.body == b""
    assert repr(response) == "ServerResponse(200 OK, 0 bytes)"


def test_the_writers_set_the_content_type_and_replace_the_body() -> None:
    response = ServerResponse()

    response.write_xml("<WMS_Capabilities/>")
    assert response.body == b"<WMS_Capabilities/>"
    assert response.header("Content-Type") == "text/xml; charset=utf-8"

    response.write_json({"layers": 2})
    assert response.body == b'{"layers": 2}'
    assert response.header("content-type") == "application/json; charset=utf-8"

    response.write_text("busy", status=503)
    assert (response.status, response.status_message) == (503, "Service Unavailable")
    assert response.body == b"busy"


def test_a_header_is_one_entry_whatever_the_case_it_was_set_with() -> None:
    response = ServerResponse().set_header("Cache-Control", "no-store")

    response.set_header("cache-control", "max-age=0")

    assert response.header("CACHE-CONTROL") == "max-age=0"
    assert list(response.headers) == ["Content-Type", "cache-control"]


def test_a_denial_names_its_reason_and_can_carry_a_challenge() -> None:
    denial = ServerResponse.denied("layer 'parcels' is internal")

    assert denial.status == 403
    assert denial.body == b"layer 'parcels' is internal"
    assert (
        ServerResponse.denied("no", www_authenticate="Basic").header("WWW-Authenticate")
        == "Basic"
    )


# -- declaring a hook --------------------------------------------------------------


def test_a_filter_works_bare_and_called() -> None:
    @filter
    def bare(ctx: ServerContext, request: ServerRequest, response: ServerResponse):
        return None

    @filter(priority=5)
    def called(ctx: ServerContext, request: ServerRequest, response: ServerResponse):
        return None

    assert declaration_of(bare) == HookDeclaration("filter", 30)
    assert declaration_of(called) == HookDeclaration("filter", 5)


def test_a_service_derives_its_ogc_name_from_the_function() -> None:
    @service
    def wms(ctx: ServerContext, request: ServerRequest) -> ServerResponse:
        return ServerResponse.xml("<ok/>")

    assert declaration_of(wms) == HookDeclaration(
        "service", 30, name="WMS", version="1.0.0"
    )


@pytest.mark.parametrize(
    ("kind", "parameters", "message"),
    [
        (
            filter,
            ("ctx", "request"),
            r"must take \(ctx, request, response\) in that order",
        ),
        (
            service,
            ("ctx", "request", "response"),
            r"must take \(ctx, request\) in that order",
        ),
        (
            access_control,
            ("ctx", "layer"),
            r"must take \(ctx, request, layer\) in that order",
        ),
    ],
)
def test_a_hook_with_the_wrong_signature_is_refused(kind, parameters, message) -> None:
    source = f"def hook({', '.join(parameters)}): ..."
    namespace: dict[str, object] = {"ServerContext": ServerContext}
    exec(source, namespace)  # noqa: S102 - the parameters are a fixed table

    with pytest.raises(QgisSdkDeclarationError, match=message):
        kind(namespace["hook"])


def test_a_hook_must_annotate_its_context() -> None:
    def unannotated(ctx, request, response):
        return None

    with pytest.raises(QgisSdkDeclarationError, match="must annotate its first"):
        filter(unannotated)


def test_an_async_hook_is_refused_with_the_reason() -> None:
    async def fetch(ctx: ServerContext, request: ServerRequest) -> ServerResponse:
        return ServerResponse()

    with pytest.raises(QgisSdkDeclarationError, match="no event loop"):
        service(fetch)


def test_a_priority_that_is_not_an_int_is_refused() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="priority must be an int"):
        filter(priority="20")  # type: ignore[arg-type]


def test_a_plain_function_is_not_a_hook() -> None:
    def helper() -> None: ...

    with pytest.raises(QgisSdkDeclarationError, match="is not a server hook"):
        ServerHooks((helper,))


def test_two_services_cannot_claim_one_name() -> None:
    @service(name="WMS")
    def first(ctx: ServerContext, request: ServerRequest) -> ServerResponse:
        return ServerResponse()

    @service(name="wms")
    def second(ctx: ServerContext, request: ServerRequest) -> ServerResponse:
        return ServerResponse()

    with pytest.raises(QgisSdkDeclarationError, match="two @server.service hooks"):
        ServerHooks((first, second))


# -- ordering ----------------------------------------------------------------------


def test_filters_run_by_priority_then_declaration_order() -> None:
    def make(name: str, priority: int):
        def hook(ctx: ServerContext, request: ServerRequest, response: ServerResponse):
            return None

        hook.__name__ = name
        return filter(hook, priority=priority)

    late = make("late", 40)
    first = make("first", 10)
    second = make("second", 10)

    hooks = ServerHooks((late, first, second))

    assert [hook.__name__ for hook in hooks.filters] == ["first", "second", "late"]


def test_included_hooks_run_after_the_plugins_own() -> None:
    def hook(name: str, priority: int):
        def body(ctx: ServerContext, request: ServerRequest, response: ServerResponse):
            return None

        body.__name__ = name
        return filter(body, priority=priority)

    parent = hook("parent", 20)
    included = hook("included", 20)

    # The host hands the included plugin's hooks after the class's own, exactly
    # as `include()` does for declarations.
    assert [hook.__name__ for hook in ServerHooks((parent, included)).filters] == [
        "parent",
        "included",
    ]


# -- the context -------------------------------------------------------------------


def test_the_context_says_it_is_the_server_host() -> None:
    scope = ResourceScope()
    ctx = ServerContext(scope, capabilities(), ServerResponse())

    assert ctx.host is Host.SERVER
    assert ctx.host.gui is False
    assert "host=server" in repr(ctx)
    assert ctx.capabilities == frozenset()


def test_a_service_the_request_project_does_not_provide_is_refused_by_name() -> None:
    ctx = ServerContext(ResourceScope(), capabilities(), ServerResponse())

    with pytest.raises(QgisSdkUnsupportedCapabilityError, match="project"):
        _ = ctx.project
    assert ctx.has("layers") is False
    with pytest.raises(ValueError, match="no capability named 'workers'"):
        ctx.has("workers")


def test_the_context_is_read_only() -> None:
    ctx = ServerContext(ResourceScope(), capabilities(), ServerResponse())

    with pytest.raises(AttributeError, match="read-only"):
        ctx.request = capabilities()  # type: ignore[misc]


# -- serving a request -------------------------------------------------------------


def served(*hooks: object) -> FakeServerInterface:
    """A fake interface the host has registered ``hooks`` with."""
    interface = FakeServerInterface()
    host = ServerHost(ServerHooks(hooks), interface)
    host.register()
    return interface


def test_registration_records_priority_and_ogc_name() -> None:
    @filter(priority=10)
    def early(ctx: ServerContext, request: ServerRequest, response: ServerResponse):
        return None

    @service(name="FIELD")
    def field(ctx: ServerContext, request: ServerRequest) -> ServerResponse:
        return ServerResponse.xml("<ok/>")

    @access_control
    def only_public(ctx: ServerContext, request: ServerRequest, layer: str) -> bool:
        return True

    interface = served(early, field, only_public)

    assert [(item.name, item.priority) for item in interface.filters] == [("early", 10)]
    assert [(name, version) for name, version, _ in interface.services] == [
        ("FIELD", "1.0.0")
    ]
    assert [item.name for item in interface.access_control] == ["only_public"]
    assert interface.registrations == {
        "filters": 1,
        "services": 1,
        "access_control": 1,
    }


def test_registering_twice_registers_nothing_new() -> None:
    @filter
    def once(ctx: ServerContext, request: ServerRequest, response: ServerResponse):
        return None

    interface = FakeServerInterface()
    host = ServerHost(ServerHooks((once,)), interface)

    host.register()
    host.register()

    assert len(interface.filters) == 1


def test_a_filter_rewrites_the_request_the_next_hook_sees() -> None:
    seen: list[str | None] = []

    @filter(priority=10)
    def default_version(ctx: ServerContext, request: ServerRequest, response):
        assert request.param("SERVICE") == "WMS"
        return request.with_params(VERSION="1.3.0")

    @filter(priority=20)
    def record(ctx: ServerContext, request: ServerRequest, response):
        seen.append(request.param("version"))

    @service(name="WMS")
    def caps(ctx: ServerContext, request: ServerRequest) -> ServerResponse:
        return ServerResponse.xml(f"<version>{request.param('VERSION')}</version>")

    answer = FakeServerInterface().serve(
        ServerHooks((default_version, record, caps)),
        request(SERVICE="WMS", REQUEST="GetCapabilities"),
    )

    assert seen == ["1.3.0"]
    assert answer.body == b"<version>1.3.0</version>"
    assert answer.header("Content-Type") == "text/xml; charset=utf-8"


def test_a_filter_that_answers_stops_the_chain() -> None:
    called: list[str] = []

    @filter(priority=10)
    def refuse(ctx: ServerContext, request: ServerRequest, response):
        called.append("refuse")
        return ServerResponse.denied("maintenance", status=503)

    @filter(priority=20)
    def never(ctx: ServerContext, request: ServerRequest, response):
        called.append("never")

    answer = FakeServerInterface().serve(ServerHooks((refuse, never)), capabilities())

    assert called == ["refuse"]
    assert (answer.status, answer.body) == (503, b"maintenance")


def test_a_service_answers_its_own_request() -> None:
    @service(name="FIELD", version="1.2.0")
    def field(ctx: ServerContext, request: ServerRequest) -> ServerResponse:
        return ServerResponse.json({"layer": request.param("LAYERS")})

    interface = FakeServerInterface()
    answer = interface.serve(
        ServerHooks((field,)), request(SERVICE="field", LAYERS="parcels")
    )

    assert answer.status == 200
    assert answer.body == b'{"layer": "parcels"}'
    assert [(name, version) for name, version, _ in interface.services] == [
        ("FIELD", "1.2.0")
    ]


def test_a_service_that_does_not_answer_with_a_response_is_a_programming_error() -> (
    None
):
    @service(name="FIELD")
    def field(ctx: ServerContext, request: ServerRequest):
        return "ok"

    with pytest.raises(QgisSdkUnsupportedCapabilityError, match="a service answers"):
        FakeServerInterface().serve(ServerHooks((field,)), request(SERVICE="FIELD"))


def test_a_filter_that_returns_something_else_is_a_programming_error() -> None:
    @filter
    def confused(ctx: ServerContext, request: ServerRequest, response):
        return 42

    with pytest.raises(QgisSdkUnsupportedCapabilityError, match="return None to pass"):
        FakeServerInterface().serve(ServerHooks((confused,)), capabilities())


def test_an_access_hook_refuses_one_layer() -> None:
    @access_control
    def parcels_are_internal(
        ctx: ServerContext, request: ServerRequest, layer: str
    ) -> bool:
        return layer != "parcels"

    @service(name="WMS")
    def getmap(ctx: ServerContext, request: ServerRequest) -> ServerResponse:
        return ServerResponse.xml("<map/>")

    interface = FakeServerInterface()

    refused = interface.serve(
        ServerHooks((parcels_are_internal, getmap)),
        request(SERVICE="WMS", REQUEST="GetMap", LAYERS="parcels"),
    )
    allowed = interface.serve(
        ServerHooks((parcels_are_internal, getmap)),
        request(SERVICE="WMS", REQUEST="GetMap", LAYERS="roads"),
    )

    assert refused.status == 403
    assert b"parcels" in refused.body
    assert (allowed.status, allowed.body) == (200, b"<map/>")


def test_an_access_hook_rules_on_every_requested_layer() -> None:
    asked: list[str] = []

    @access_control
    def record(ctx: ServerContext, request: ServerRequest, layer: str) -> bool:
        asked.append(layer)
        return True

    FakeServerInterface().serve(
        ServerHooks((record,)),
        request(SERVICE="WMS", REQUEST="GetMap", LAYERS="roads, parcels ,rivers"),
    )

    assert asked == ["roads", "parcels", "rivers"]


def test_an_access_hook_may_write_its_own_refusal() -> None:
    @access_control
    def locked(ctx: ServerContext, request: ServerRequest, layer: str) -> bool:
        ctx.response.write_xml("<ServiceException>locked</ServiceException>")
        ctx.response.set_status(451)
        return False

    answer = FakeServerInterface().serve(
        ServerHooks((locked,)), request(SERVICE="WMS", LAYERS="parcels")
    )

    assert answer.status == 451
    assert answer.body == b"<ServiceException>locked</ServiceException>"


def test_a_service_nobody_serves_is_a_named_400() -> None:
    answer = FakeServerInterface().serve(ServerHooks(), request(SERVICE="GEOJSON"))

    assert answer.status == 400
    assert b"GEOJSON" in answer.body
    assert b"not served by this plugin" in answer.body


def test_a_host_that_owns_its_scope_closes_it_when_the_response_exists() -> None:
    scopes: list[ResourceScope] = []

    @filter
    def remember(ctx: ServerContext, request: ServerRequest, response):
        scopes.append(ctx.scope)

    answer = FakeServerInterface().serve(ServerHooks((remember,)), capabilities())

    assert answer.status == 400
    assert [scope.closed for scope in scopes] == [True]


def test_a_caller_that_owns_the_scope_keeps_it_open() -> None:
    scope = ResourceScope()

    FakeServerInterface().serve(ServerHooks(), capabilities(), scope=scope)

    assert scope.closed is False
    scope.close()


def test_a_context_factory_replaces_the_services_a_request_carries() -> None:
    seen: list[object] = []

    @filter
    def read_project(ctx: ServerContext, request: ServerRequest, response):
        seen.append(ctx.project)

    host = ServerHost(
        ServerHooks((read_project,)),
        FakeServerInterface(),
        context_factory=lambda scope, request, response: ServerContext(
            scope,
            request,
            response,
            project=object(),  # type: ignore[arg-type]
        ),
    )

    host.handle(capabilities())

    assert seen and seen[0] is not None
