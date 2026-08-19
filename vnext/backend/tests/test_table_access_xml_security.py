"""XML security refusal tests. Documents never fetch external resources."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from gateway_backend.capabilities.table_access.contracts import ParseStatus, ParserDiagnosticCode
from tests.support.table_access_xml import parse_xml_text

XML_SECURITY_PAYLOADS = (
    (
        "doctype",
        b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE foo>\n<root/>\n",
        ParserDiagnosticCode.XML_DTD_FORBIDDEN,
        "DOCTYPE",
    ),
    (
        "internal-entity",
        b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE foo [
  <!ENTITY xxe "ssn">
]>
<root>&xxe;</root>
""",
        ParserDiagnosticCode.XML_EXTERNAL_ENTITY_FORBIDDEN,
        "entities",
    ),
    (
        "external-entity",
        b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "xxe.txt">
]>
<root>&xxe;</root>
""",
        ParserDiagnosticCode.XML_EXTERNAL_ENTITY_FORBIDDEN,
        "entities",
    ),
    (
        "file-uri",
        b'<?xml version="1.0"?><!DOCTYPE foo SYSTEM "file:///etc/passwd"><root/>',
        ParserDiagnosticCode.XML_NETWORK_FORBIDDEN,
        "external resource",
    ),
    (
        "http-uri",
        b'<?xml version="1.0"?><!DOCTYPE foo SYSTEM "http://example.invalid/xxe"><root/>',
        ParserDiagnosticCode.XML_NETWORK_FORBIDDEN,
        "external resource",
    ),
    (
        "ftp-uri",
        b'<?xml version="1.0"?><!DOCTYPE foo SYSTEM "ftp://example.invalid/x"><root/>',
        ParserDiagnosticCode.XML_NETWORK_FORBIDDEN,
        "external resource",
    ),
    (
        "xinclude",
        b'<xi:include xmlns:xi="http://www.w3.org/2001/XInclude" href="file:///etc/passwd"/>',
        ParserDiagnosticCode.XML_XINCLUDE_FORBIDDEN,
        "XInclude",
    ),
    (
        "xinclude-child",
        b'<root xmlns:xi="http://www.w3.org/2001/XInclude"><xi:include href="http://example.invalid"/></root>',
        ParserDiagnosticCode.XML_XINCLUDE_FORBIDDEN,
        "XInclude",
    ),
)

VECTOR_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "vectors" / "table-access" / "xml-security" / "v1"
)


@pytest.mark.parametrize(
    ("case_id", "payload", "code", "needle"),
    XML_SECURITY_PAYLOADS,
    ids=[item[0] for item in XML_SECURITY_PAYLOADS],
)
def test_xml_security_payloads_fail_closed(
    case_id: str, payload: bytes, code: ParserDiagnosticCode, needle: str
) -> None:
    del case_id
    result = parse_xml_text(payload)
    assert result.status is ParseStatus.FAILED
    assert result.events == ()
    assert result.diagnostics[0].code is code
    assert needle in result.diagnostics[0].message


def test_xml_security_vector_file_matches_parameter_table() -> None:
    payload = json.loads((VECTOR_ROOT / "cases.json").read_text(encoding="utf-8"))
    names = [item[0] for item in XML_SECURITY_PAYLOADS]
    assert payload["cases"] == names
