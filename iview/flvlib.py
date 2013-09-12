from .utils import fastforward, CounterWriter
from struct import Struct
from .utils import read_int
from .utils import setitem

def main():
    from sys import stdin
    flv = stdin.buffer
    print("signature", flv.read(3))
    (version, flags) = flv.read(2)
    audio = bool(flags & 1 << 2)
    video = bool(flags & 1 << 0)
    print("version", version, "audio", audio, "video", video)
    body = read_int(flv, 4)
    fastforward(flv, body - 9)
    
    while True:
        fastforward(flv, 4)  # Previous tag size
        tag = read_tag_header(flv)
        if tag is None:
            break
        print(repr(tag))
        
        parser = tag_parsers.get(tag["type"])
        if parser:
            parsed = parser(flv, tag)
            print(" ", repr(parsed))
        fastforward(flv, tag["length"])

def write_file_header(flv, audio=True, video=True):
    counter = CounterWriter(flv)
    counter.write(b"FLV")  # Signature
    counter.write(bytes((1,)))  # File version
    counter.write(bytes((audio << 2 | video << 0,)))
    
    flv.write((counter.tell() + 4).to_bytes(4, "big"))  # Body offset
    flv.write((0).to_bytes(4, "big"))  # Previous tag size

def write_scriptdata(flv, metadata):
    counter = CounterWriter(flv)
    counter.write(bytes((TAG_SCRIPTDATA,)))
    counter.write(len(metadata).to_bytes(3, "big"))
    counter.write((0).to_bytes(3, "big"))  # Timestamp
    counter.write(bytes((0,)))  # Timestamp extension
    counter.write((0).to_bytes(3, "big"))  # Stream id
    counter.write(metadata)
    flv.write(counter.tell().to_bytes(4, "big"))

def read_tag_header(flv):
    flags = flv.read(1)
    if not flags:
        return None
    (flags,) = flags
    length = read_int(flv, 3)
    timestamp = read_int(flv, 3)
    (extension,) = SBYTE.unpack(flv.read(1))
    streamid = read_int(flv, 3)
    return dict(
        filter=bool(flags >> 5 & 1),
        type=flags >> 0 & 0x1F,
        length=length,
        timestamp=timestamp | extension << 24,
        streamid=streamid,
    )
SBYTE = Struct("=b")

tag_parsers = dict()

TAG_AUDIO = 8
@setitem(tag_parsers, TAG_AUDIO)
def parse_audio_tag(flv, tag):
    (flags,) = flv.read(1)
    tag["length"] -= 1
    result = dict(
        format=flags >> 4 & 0xF,
        rate=flags >> 2 & 3,
        size=flags >> 1 & 1,
        type=flags >> 0 & 1,
    )
    if result["format"] == FORMAT_AAC:
        (result["aac_type"],) = flv.read(1)
        tag["length"] -= 1
    return result

FORMAT_AAC = 10
AAC_HEADER = 0

TAG_VIDEO = 9
@setitem(tag_parsers, TAG_VIDEO)
def parse_video_tag(flv, tag):
    (flags,) = flv.read(1)
    tag["length"] -= 1
    result = dict(
        frametype=flags >> 4 & 0xF,
        codecid=flags >> 0 & 0xF,
    )
    if result["codecid"] == CODEC_AVC:
        (result["avc_type"],) = flv.read(1)
        tag["length"] -= 1
    return result

CODEC_AVC = 7
AVC_HEADER = 0

TAG_SCRIPTDATA = 18
@setitem(tag_parsers, TAG_SCRIPTDATA)
def parse_scriptdata(stream, tag=None):
    name = parse_scriptdatavalue(stream)
    value = parse_scriptdatavalue(stream)
    if tag is not None:
        tag["length"] = 0
    return dict(name=name, value=value)

def parse_scriptdatavalue(stream):
    type = read_int(stream, 1)
    return scriptdatavalue_parsers[type](stream)

scriptdatavalue_parsers = dict()

@setitem(scriptdatavalue_parsers, 0)
def parse_number(stream):
    (number,) = DOUBLE_BE.unpack(stream.read(DOUBLE_BE.size))
    return number
DOUBLE_BE = Struct(">d")

@setitem(scriptdatavalue_parsers, 1)
def parse_boolean(stream):
    return bool(read_int(stream, 1))

@setitem(scriptdatavalue_parsers, 2)
def parse_string(stream):
    length = read_int(stream, 2)
    string = stream.read(length)
    assert len(string) == length
    return string

@setitem(scriptdatavalue_parsers, 3)
def parse_object(stream):
    array = dict()
    while True:
        name = parse_string(stream)
        value = parse_scriptdatavalue(stream)
        if value is StopIteration:
            return array
        array[name.decode("ascii")] = value

@setitem(scriptdatavalue_parsers, 8)
def parse_ecma_array(stream):
    fastforward(stream, 4)  # Approximate length
    return parse_object(stream)

@setitem(scriptdatavalue_parsers, 9)
def parse_end(stream):
    return StopIteration

@setitem(scriptdatavalue_parsers, 10)
def parse_array(stream):
    length = read_int(stream, 4)
    return tuple(parse_scriptdatavalue(stream) for _ in range(length))

if __name__ == "__main__":
    main()
