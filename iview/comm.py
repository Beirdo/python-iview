import os
import urllib2
import gtk
import config
import parser
import rc4

cache = False

iview_config = None
channels = None

# name, id, url, description
programme = gtk.TreeStore(str, str, str, str)

def fetch_url(url):
	"""	Simple function that fetches a URL using urllib2.
		An exception is raised if an error (e.g. 404) occurs.
	"""
	http = urllib2.urlopen(urllib2.Request(url, None, {'User-Agent' : config.user_agent}))
	return http.read()

def maybe_fetch(url):
	"""	Only fetches a URL if it is not in the cache/ directory.
		In practice, this is really bad, and only useful for saving
		bandwidth when debugging. For one, it doesn't respect
		HTTP's wishes. Also, iView, by its very nature, changes daily.
	"""

	if not cache:
		return fetch_url(url)

	if not os.path.isdir('cache'):
		os.mkdir('cache')

	filename = os.path.join('cache', url.split('/')[-1])

	if os.path.isfile(filename):
		f = open(filename, 'r')
		data = f.read()
		f.close()
	else:
		data = fetch_url(url)
		f = open(filename, 'w')
		f.write(data)
		f.flush()
		os.fsync(f.fileno())
		f.close()

	return data

def get_config():
	"""	This function fetches the iView "config". Among other things,
		it tells us an always-metered "fallback" RTMP server, and points
		us to many of iView's other XML files.
	"""
	global iview_config, channels

	iview_config = parser.parse_config(maybe_fetch(config.config_url))

def get_auth():
	""" This function performs an authentication handshake with iView.
		Among other things, it tells us if the connection is unmetered,
		and gives us a one-time token we need to use to speak RTSP with
		ABC's servers, and tells us what the RTMP URL is.
	"""
	return parser.parse_auth(fetch_url(config.auth_url))

def get_programme(progress=None):
	"""	This function pulls in the index, which contains the TV series
		that are available to us. The index is possibly encrypted, so we
		must decrypt it here before passing it to the parser.
	"""
	global programme

	index_xml = maybe_fetch(iview_config['index_url'])

	if config.use_encryption:
		r = rc4.RC4(config.index_password)
		# RC4 is bidirectional, no need to distinguish between 'encrypt'
		# and 'decrypt'.
		index_xml = r.engine_crypt(r.hex_to_str(index_xml))

	index = parser.parse_index(index_xml, programme)

def get_series_items(series_iter):
	"""	This function fetches the series detail page for the selected series,
		which contain the items (i.e. the actual episodes).
	"""
	global programme

	series_id = programme.get(series_iter, 1)[0]

	series_xml = maybe_fetch(config.series_url % series_id)
	parser.parse_series_items(series_iter, series_xml, programme)


def get_highlights():

	highlightXML = maybe_fetch(config.highlights_url)
	return parser.parse_highlights(highlightXML)

def get_categories(self):
	categoriesXML = str(maybe_fetch(config.categories_url))
	return parser.parse_categories(categoriesXML)
