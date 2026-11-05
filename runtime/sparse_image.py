import argparse
import gzip
import struct
import tarfile
from pathlib import Path


def read_exact(source, size):
    data = source.read(size)
    if len(data) != size:
        raise ValueError(f"Truncated image: expected {size}, received {len(data)} bytes")
    return data


def convert(source, destination):
    header = read_exact(source, 28)
    magic, major, minor, header_size, chunk_header_size, block_size, blocks, chunks, checksum = struct.unpack("<I4H4I", header)
    if magic != 0xED26FF3A or major != 1 or header_size < 28 or chunk_header_size < 12 or block_size == 0:
        raise ValueError("Unsupported Android sparse image header")
    read_exact(source, header_size - 28)
    written_blocks = 0
    for chunk_number in range(chunks):
        chunk_header = read_exact(source, chunk_header_size)
        chunk_type, reserved, chunk_blocks, total_size = struct.unpack("<2H2I", chunk_header[:12])
        data_size = total_size - chunk_header_size
        output_size = chunk_blocks * block_size
        if data_size < 0:
            raise ValueError("Invalid sparse chunk size")
        if chunk_type == 0xCAC1:
            if data_size != output_size:
                raise ValueError("Invalid raw chunk")
            remaining = data_size
            while remaining:
                data = read_exact(source, min(remaining, 1024 * 1024))
                destination.write(data)
                remaining -= len(data)
        elif chunk_type == 0xCAC2:
            if data_size != 4 or output_size % 4:
                raise ValueError("Invalid fill chunk")
            pattern = read_exact(source, 4)
            buffer = pattern * (256 * 1024)
            remaining = output_size
            while remaining:
                amount = min(remaining, len(buffer))
                destination.write(buffer[:amount])
                remaining -= amount
        elif chunk_type == 0xCAC3:
            if data_size:
                raise ValueError("Invalid don't-care chunk")
            destination.seek(output_size, 1)
        elif chunk_type == 0xCAC4:
            if data_size != 4 or chunk_blocks:
                raise ValueError("Invalid CRC chunk")
            read_exact(source, 4)
        else:
            raise ValueError(f"Unknown chunk type {chunk_type:#x}")
        written_blocks += chunk_blocks
    if written_blocks != blocks:
        raise ValueError("Sparse image block count mismatch")
    if source.read(1):
        raise ValueError("Unexpected data after the last sparse chunk")
    destination.truncate(blocks * block_size)
    return blocks * block_size


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--member")
    arguments = parser.parse_args()
    temporary = arguments.output.with_suffix(".partial")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(arguments.archive) as archive:
            members = [member for member in archive.getmembers() if member.name.endswith(".ext4.simg.bin.gz") and member.isfile()]
            if arguments.member:
                members = [member for member in members if member.name == arguments.member]
            if len(members) != 1:
                raise ValueError(f"Expected one filesystem image, found {len(members)}")
            with archive.extractfile(members[0]) as compressed:
                with gzip.GzipFile(fileobj=compressed) as source, temporary.open("wb") as destination:
                    size = convert(source, destination)
        temporary.replace(arguments.output)
        print(f"Converted {members[0].name}: {size} bytes", flush=True)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()
