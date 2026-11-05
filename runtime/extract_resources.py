import argparse
import gzip
import hashlib
import json
import shutil
import stat
import struct
import zlib
from pathlib import Path, PurePosixPath


def safe_relative(name):
    path = PurePosixPath(name)
    if ".." in path.parts or "\\" in name or "\0" in name:
        raise ValueError(f"Unsafe archive path: {name!r}")
    return Path(*[part for part in path.parts if part != "/"])


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def extract_g80(source, destination):
    blob = source.read_bytes()
    if blob[0x200:0x208] != b"HAR#$%&@":
        raise ValueError("Unexpected G80 archive header")
    if int.from_bytes(blob[1:5], "big") != 0x987F or blob[5:8] != bytes((36, 10, 4)):
        raise ValueError("G80 package identity/version mismatch")
    destination.mkdir()
    root = destination / "rootfs"
    root.mkdir()
    offset = 0x200
    records = []
    segments = 0
    manifest = None
    while offset < len(blob):
        if blob[offset:offset + 8] == b"HAR#$%&@":
            if offset + 64 > len(blob):
                raise ValueError("Truncated segment header")
            segments += 1
            offset += 64
            continue
        if blob[offset:offset + 4] != b"\0\0P\x12" or offset + 120 > len(blob):
            raise ValueError(f"Unexpected archive record at {offset:#x}")
        name_length = struct.unpack_from("<I", blob, offset + 4)[0]
        packed_size = struct.unpack_from("<I", blob, offset + 12)[0]
        unpacked_size = struct.unpack_from("<I", blob, offset + 16)[0]
        mode = struct.unpack_from("<I", blob, offset + 60)[0]
        name_start = offset + 92
        payload_start = offset + 120 + name_length
        payload_end = payload_start + packed_size
        if not 0 < name_length < 4096 or payload_end > len(blob):
            raise ValueError("Invalid record bounds")
        name = blob[name_start:name_start + name_length].decode("utf-8")
        relative = safe_relative(name)
        target = root / relative
        if target.exists() or target.is_symlink():
            raise ValueError(f"Duplicate archive member: {name}")
        if packed_size:
            decoder = zlib.decompressobj()
            payload = decoder.decompress(blob[payload_start:payload_end], unpacked_size + 1)
            if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                raise ValueError(f"Invalid compressed member: {name}")
        else:
            payload = b""
        if len(payload) != unpacked_size:
            raise ValueError(f"Expanded size mismatch: {name}")
        if stat.S_ISDIR(mode):
            if payload:
                raise ValueError("Directory record has payload")
            target.mkdir(parents=True)
        elif stat.S_ISREG(mode):
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(payload)
            if name.endswith(".manifest"):
                manifest = payload.decode("utf-8")
        else:
            raise ValueError(f"Unsupported archive member type: {name}")
        target.chmod(stat.S_IMODE(mode) & 0o777)
        records.append({"path": name, "size": unpacked_size, "mode": oct(mode)})
        offset = payload_end
    if manifest is None:
        raise ValueError("G80 content manifest missing")
    manifest_files = []
    for line in manifest.splitlines():
        fields = [field.strip() for field in line.split("|")]
        if len(fields) != 3 or fields[0] != "-":
            continue
        target = root / "mnt/dataro/data" / safe_relative(fields[1])
        actual_hash = digest(target)
        manifest_files.append({"path": fields[1], "sha256": actual_hash, "embedded_digest": fields[2], "plain_sha256_matches_embedded_digest": actual_hash == fields[2].lower()})
    content_records = [record for record in records if record["path"].startswith("/mnt/dataro/data/") and stat.S_ISREG(int(record["mode"], 8))]
    if len(manifest_files) != len(content_records):
        raise ValueError("Manifest does not cover every G80 content file")
    result = {
        "package": "swfk_0000987f_036_010_004",
        "role": "preferred-g80",
        "source": str(source),
        "source_sha256": digest(source),
        "format": "HAR records with zlib payloads",
        "segments": segments,
        "records": len(records),
        "zlib_checksum_verified_files": sum(record["size"] > 0 for record in records),
        "manifest_content_files": len(manifest_files),
        "manifest_digest_semantics": "Embedded digests do not match plain file SHA-256; algorithm/metadata coverage not established",
        "content_files": manifest_files,
        "content_root": "rootfs/mnt/dataro/data/hmi8/vehicles/widgetasset/vehicles/G80",
        "signature_authenticated": False,
        "runtime_compatibility": "Not established; original target is eMMCDataRO, unlike MGU22 BEGU images",
    }
    (destination / "extraction.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def decompress_ext4(manifest_path, destination):
    manifest = json.loads(manifest_path.read_text())
    artifacts = manifest["artifacts"]
    if len(artifacts) != 1:
        raise ValueError("Expected one resource image per package")
    artifact = artifacts[0]
    if Path(artifact["name"]).name != artifact["name"]:
        raise ValueError("Unsafe artifact name")
    source = manifest_path.parent / artifact["name"]
    actual_hash = digest(source)
    if source.stat().st_size != artifact["size"] or actual_hash != artifact["hash"].lower():
        raise ValueError(f"Compressed artifact integrity mismatch: {source}")
    destination.mkdir()
    for metadata in manifest_path.parent.glob("*.json"):
        shutil.copyfile(metadata, destination / metadata.name)
    for signature in manifest_path.parent.glob("*.sig"):
        shutil.copyfile(signature, destination / signature.name)
    image = destination / artifact["name"].removesuffix(".bin.gz")
    temporary = image.with_suffix(".partial")
    with gzip.open(source, "rb") as compressed, temporary.open("xb") as output:
        shutil.copyfileobj(compressed, output, 1024 * 1024)
    with temporary.open("rb") as stream:
        stream.seek(1080)
        if stream.read(2) != b"\x53\xef":
            raise ValueError("Decompressed image is not ext4")
    temporary.replace(image)
    result = {
        "package": manifest_path.stem,
        "source": str(source),
        "compressed_sha256": actual_hash,
        "manifest_hash_verified": True,
        "signature_authenticated": False,
        "image": image.name,
        "image_size": image.stat().st_size,
        "image_sha256": digest(image),
        "begu_image_name": artifact["custom"]["name"],
        "rootfs_exported": False,
    }
    (destination / "extraction.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--research", type=Path, default=Path(__file__).resolve().parent.parent)
    arguments = parser.parse_args()
    source = arguments.research / "mgu22filesystem/originalfiles"
    output = arguments.research / "mgu22filesystem/extracted"
    packages = [
        ("swfk_0000987f_036_010_004", source / "swfk_0000987f.bin.036_010_004"),
        *[(name, source / name / "full" / f"{name}.json") for name in (
            "swfk_0000a6b0_007_023_004", "swfk_0000a6b1_007_023_004",
            "swfk_0000aed4_007_023_004", "swfk_00009fd1_007_020_007",
            "swfk_0000a7e4_007_020_007", "swfk_0000a7e6_007_020_007",
        )],
    ]
    for name, path in packages:
        destination = output / name
        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite existing package: {destination}")
        result = extract_g80(path, destination) if path.name.startswith("swfk_0000987f.bin") else decompress_ext4(path, destination)
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
