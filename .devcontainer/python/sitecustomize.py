"""Local TLS compatibility for the corporate Zscaler root certificate."""

import os
import ssl


if os.environ.get("BMW_STATUS_ZSCALER_COMPAT") == "1":
    _create_default_context = ssl.create_default_context


    def create_default_context(*args, **kwargs):
        """Keep TLS validation enabled while accepting the legacy Zscaler CA."""
        context = _create_default_context(*args, **kwargs)
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        return context


    ssl.create_default_context = create_default_context
    ssl._create_default_https_context = create_default_context