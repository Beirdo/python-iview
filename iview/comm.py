import os
import sys
from . import config
from . import parser
import gzip
from io import BytesIO
# "urllib.request" is imported at end
from urllib.parse import urljoin, urlsplit
from urllib.parse import quote_plus, urlencode


iview_config = None

def fetch_url(url):
	"""	Simple function that fetches a URL using urllib.
		An exception is raised if an error (e.g. 404) occurs.
	"""
	url = urljoin(config.base_url, url)
	http = urllib.request.urlopen(
		urllib.request.Request(url, None, iview_config['headers'])
	)
	headers = http.info()
	if 'content-encoding' in headers and headers['content-encoding'] == 'gzip':
		data = BytesIO(http.read())
		return gzip.GzipFile(fileobj=data).read()
	else:
		return http.read()

def maybe_fetch(url):
	"""	Only fetches a URL if it is not in the cache directory.
		In practice, this is really bad, and only useful for saving
		bandwidth when debugging. For one, it doesn't respect
		HTTP's wishes. Also, iView, by its very nature, changes daily.
	"""

	if not config.cache:
		return fetch_url(url)

	if not os.path.isdir(config.cache):
		os.mkdir(config.cache)

	filename = os.path.join(config.cache, url.split('/')[-1])

	if os.path.isfile(filename):
		f = open(filename, 'rb')
		data = f.read()
		f.close()
	else:
		data = fetch_url(url)
		f = open(filename, 'wb')
		f.write(data)
		f.flush()
		os.fsync(f.fileno())
		f.close()

	return data

def get_config(headers=dict()):
	"""	This function fetches the iView "config". Among other things,
		it tells us an always-metered "fallback" RTMP server, and points
		us to many of iView's other XML files.
	"""
	global iview_config

	try:
		headers['User-Agent'] = headers['User-Agent'] + ' '
	except LookupError:
		headers['User-Agent'] = ''
	headers['User-Agent'] += config.user_agent
	headers['Accept-Encoding'] = 'gzip'
	iview_config = dict(headers=headers)
	
	parsed = parser.parse_config(maybe_fetch(config.config_url))
	iview_config.update(parsed)

def get_auth():
	""" This function performs an authentication handshake with iView.
		Among other things, it tells us if the connection is unmetered,
		and gives us a one-time token we need to use to speak RTSP with
		ABC's servers, and tells us what the RTMP URL is.
	"""
	auth = iview_config['auth_url']
	if config.ip:
		query = urlsplit(auth).query
		query = query and query + "&"
		query += urlencode((("ip", config.ip),))
		auth = urljoin(auth, "?" + query)
	auth = fetch_url(auth)
	return parser.parse_auth(auth, iview_config)

def get_categories():
	"""Returns the list of categories
	"""
	url = iview_config['categories_url']
	category_data = maybe_fetch(url)
	categories = parser.parse_categories(category_data)
	return categories

def get_index():
	"""	This function pulls in the index, which contains the TV series
		that are available to us. Returns a list of "dict" objects,
		one for each series.
	"""
	return series_api('seriesIndex')

def get_series_items(series_id, get_meta=False):
	"""	This function fetches the series detail page for the selected series,
		which contain the items (i.e. the actual episodes). By
		default, returns a list of "dict" objects, one for each
		episode. If "get_meta" is set, returns a tuple with the first
		element being the list of episodes, and the second element a
		"dict" object of series infomation.
	"""

	meta = series_api('series', series_id)

	# Bad series number returns empty json string, ignore it.
	if not meta:
		print('no results for series id %s, skipping' % series_id, file=sys.stderr)
		return []
	
	(meta,) = meta
	items = meta['items']
	if get_meta:
		return (items, meta)
	else:
		return items

def get_keyword(keyword):
	return series_api('keyword', keyword)

def series_api(key, value=None):
	query = quote_plus(key)
	if value is not None:
		query += "=" + quote_plus(value)
	url = urljoin(iview_config['api_url'], '?' + query)
	index_data = maybe_fetch(url)
	return parser.parse_series_api(index_data)

def get_highlights():

	highlightXML = maybe_fetch(iview_config['highlights'])
	return parser.parse_highlights(highlightXML)

def get_captions(url):
	"""	This function takes a program name (e.g. news/730report_100803) and
		fetches the corresponding captions file. It then passes it to
		parse_subtitle(), which converts it to SRT format.
	"""

	captions_url = iview_config['captions_url'] + '%s.xml'

	xml = maybe_fetch(captions_url % url)
	return parser.parse_captions(xml)

def configure_socks_proxy():
	"""	Import the modules necessary to support usage of a SOCKS proxy
		and configure it using the current settings in iview.config
		NOTE: It would be safe to call this function multiple times
		from, say, a GTK settings dialog
	"""
	try:
		import socks
		import socket
		socket.socket = socks.socksocket
	except:
		sys.excepthook(*sys.exc_info())
		print("The Python SOCKS client module is required for proxy support.", file=sys.stderr)
		sys.exit(3)

	socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, config.socks_proxy_host, config.socks_proxy_port)

if config.socks_proxy_host is not None:
	configure_socks_proxy()

# must be done after the (optional) SOCKS proxy is configured
import urllib.request
from urllib.error import HTTPError
