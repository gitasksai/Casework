import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12

import tls_cert


def test_self_signed_loads_into_ssl_context(tmp_path):
    cert = tls_cert.make_self_signed(str(tmp_path), ["casework.example.local", "localhost"], ["10.0.0.5"])
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "casework.example.local" in san.get_values_for_type(x509.DNSName)
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(tmp_path / "cert.pem", tmp_path / "key.pem")
    assert (tmp_path / "casework.crt").exists()


def test_convert_pfx_keeps_intermediates_drops_root(tmp_path):
    # build root -> intermediate -> leaf, using the self-signed helper for keys/certs
    root = tls_cert.make_self_signed(str(tmp_path / "root"), ["root"], [])
    root_key = serialization.load_pem_private_key((tmp_path / "root" / "key.pem").read_bytes(), None)
    leaf = tls_cert.make_self_signed(str(tmp_path / "leaf"), ["leaf"], [])
    leaf_key = serialization.load_pem_private_key((tmp_path / "leaf" / "key.pem").read_bytes(), None)
    # re-sign leaf as issued by an "intermediate" (root key reused, different subject)
    inter_name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "intermediate")])
    inter = (x509.CertificateBuilder().subject_name(inter_name).issuer_name(root.subject)
             .public_key(root_key.public_key()).serial_number(1)
             .not_valid_before(root.not_valid_before_utc).not_valid_after(root.not_valid_after_utc)
             .sign(root_key, hashes.SHA256()))
    pfx = pkcs12.serialize_key_and_certificates(
        b"casework", leaf_key, leaf, [inter, root],
        serialization.BestAvailableEncryption(b"pw"))
    (tmp_path / "c.pfx").write_bytes(pfx)

    tls_cert.convert_pfx(str(tmp_path / "c.pfx"), str(tmp_path / "out"), "pw")
    pem = (tmp_path / "out" / "cert.pem").read_bytes()
    certs = x509.load_pem_x509_certificates(pem)
    assert [c.subject for c in certs] == [leaf.subject, inter.subject]
    ssl.create_default_context(ssl.Purpose.CLIENT_AUTH).load_cert_chain(
        tmp_path / "out" / "cert.pem", tmp_path / "out" / "key.pem")
