import zlib
from io import BufferedIOBase
from urllib.parse import quote_plus
from io import SEEK_CUR
import urllib.request
from http.client import HTTPConnection
import http.client

def xml_text_elements(parent, namespace=""):
	"""Extracts text from Element Tree into a dict()
	
	Each key is the tag name of a child of the given parent element, and
	the value is the text of that child. Only tags with no attributes are
	included. If the "namespace" parameter is given, it should specify an
	XML namespace enclosed in curly brackets {. . .}, and only tags in
	that namespace are included."""
	
	d = dict()
	for child in parent:
		if child.tag.startswith(namespace) and not child.keys():
			tag = child.tag[len(namespace):]
			d[tag] = child.text or ""
	return d

def read_int(stream, size):
    bytes = stream.read(size)
    assert len(bytes) == size
    return int.from_bytes(bytes, "big")

def read_string(stream):
    buf = bytearray()
    while True:
        b = stream.read(1)
        assert b
        if not ord(b):
            return buf
        buf.extend(b)

value_unsafe = '%+&;#'
VALUE_SAFE = ''.join(chr(c) for c in range(33, 127)
    if chr(c) not in value_unsafe)
def urlencode_param(value):
    """Minimal URL encoding for query parameter"""
    return quote_plus(value, safe=VALUE_SAFE)

class CounterWriter(BufferedIOBase):
    def __init__(self, output):
        self.length = 0
        self.output = output
    def write(self, b):
        self.length += len(b)
        return self.output.write(b)
    def tell(self):
        return self.length

class ZlibDecompressorWriter(BufferedIOBase):
    def __init__(self, output, *pos, buffer_size=0x10000, **kw):
        self.output = output
        self.buffer_size = buffer_size
        self.decompressor = zlib.decompressobj(*pos, **kw)
    def write(self, b):
        while b:
            data = self.decompressor.decompress(b, self.buffer_size)
            self.output.write(data)
            b = self.decompressor.unconsumed_tail
    def close(self):
        self.decompressor.flush()

class TeeWriter(BufferedIOBase):
    def __init__(self, *outputs):
        self.outputs = outputs
    def write(self, b):
        for output in self.outputs:
            output.write(b)

def streamcopy(input, output, length):
    assert length >= 0
    while length:
        chunk = input.read(min(length, 0x10000))
        assert chunk
        output.write(chunk)
        length -= len(chunk)

def fastforward(stream, offset):
    assert offset >= 0
    if stream.seekable():
        stream.seek(offset, SEEK_CUR)
    else:
        while offset:
            chunk = stream.read(min(offset, 0x10000))
            assert chunk
            offset -= len(chunk)

class WritingReader(BufferedIOBase):
    """Filter for a reader stream that writes the data read to another stream
    """
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
    def read(self, n):
        data = self.reader.read(n)
        self.writer.write(data)
        return data

def setitem(dict, key):
    """Decorator that adds the definition to a dictionary with a given key"""
    def decorator(func):
        dict[key] = func
        return func
    return decorator

class PersistentConnectionHandler(urllib.request.BaseHandler):
    """URL handler for HTTP persistent connections
    
    connection = PersistentConnectionHandler()
    session = urllib.request.build_opener(connection)
    
    # First request opens connection
    with session.open("http://localhost/one") as response:
        response.read()
    
    # Subsequent requests reuse the existing connection, unless it got closed
    with session.open("http://localhost/two") as response:
        response.read()
    
    # Closes old connection when new host specified
    with session.open("http://example/three") as response:
        response.read()
    
    connection.close()  # Frees socket
    """
    
    def __init__(self, *pos, **kw):
        self._type = None
        self._host = None
        self._pos = pos
        self._kw = kw
        self._connection = None
    
    def default_open(self, req):
        if req.type != "http":
            return None
        
        if req.type != self._type or req.host != self._host:
            if self._connection:
                self._connection.close()
            self._connection = HTTPConnection(req.host,
                *self._pos, **self._kw)
            self._type = req.type
            self._host = req.host
        
        headers = dict(req.header_items())
        try:
            return self._openattempt(req, headers)
        except http.client.BadStatusLine as err:
            # If the server closed the connection before receiving this
            # request, the "http.client" module raises an exception with the
            # "line" attribute set to repr("")!
            if err.line != repr(""):
                raise
        self._connection.close()
        return self._openattempt(req, headers)
    
    def _openattempt(self, req, headers):
        """Attempt a request using any existing connection"""
        self._connection.request(req.get_method(), req.selector, req.data,
            headers)
        response = self._connection.getresponse()
        
        # Odd impedance mismatch between "http.client" and "urllib.request"
        response.msg = response.reason
        
        return response
    
    def close(self):
        if self._connection:
            self._connection.close()
    
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        self.close()
