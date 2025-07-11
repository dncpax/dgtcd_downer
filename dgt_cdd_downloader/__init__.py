def classFactory(iface):
    """
    Load DgtCddDownloaderPlugin class from file dgt_cdd_downloader_plugin.
    """
    from .dgt_cdd_downloader_plugin import DgtCddDownloaderPlugin
    return DgtCddDownloaderPlugin(iface)
