# -*- coding: utf-8 -*-
# Copyright (c) 2015, imageio contributors
# imageio is distributed under the terms of the (new) BSD License.

""" Plugin that wraps the freeimage lib. The wrapper for Freeimage is
part of the core of imageio, but it's functionality is exposed via
the plugin system (therefore this plugin is very thin).
"""

from __future__ import absolute_import, print_function, division

import numpy as np


from .. import formats
from ..core import Format, image_as_uint8
from ._freeimage import fi, IO_FLAGS, FNAME_PER_PLATFORM  # noqa


# todo: support files with only meta data
# todo: multi-page files


class FreeimageFormat(Format):
    """ This is the default format used for FreeImage. Each Freeimage
    format has the 'flags' keyword argument. See the Freeimage
    documentation for more information.
    
    Parameters for reading
    ----------------------
    flags : int
        A freeimage-specific option. In most cases we provide explicit
        parameters for influencing image reading.
    
    Parameters for saving
    ----------------------
    flags : int
        A freeimage-specific option. In most cases we provide explicit
        parameters for influencing image saving.
    """
    
    _modes = 'i'
    
    @property
    def fif(self):
        return self._fif  # Set when format is created
    
    def _can_read(self, request):
        modes = self._modes + '?'
        if fi and request.mode[1] in modes:
            if not hasattr(request, '_fif'):
                try:
                    request._fif = fi.getFIF(request.filename, 'r', 
                                             request.firstbytes)
                except Exception:  # pragma: no cover
                    request._fif = -1
            if request._fif == self.fif:
                return True
    
    def _can_write(self, request):
        modes = self._modes + '?'
        if fi and request.mode[1] in modes:
            if not hasattr(request, '_fif'):
                try:
                    request._fif = fi.getFIF(request.filename, 'w')
                except Exception:  # pragma: no cover
                    request._fif = -1
            if request._fif is self.fif:
                return True
    
    # --
    
    class Reader(Format.Reader):
        
        def _get_length(self):
            return 1
        
        def _open(self, flags=0):
            self._bm = fi.create_bitmap(self.request.filename, 
                                        self.format.fif, flags)
            self._bm.load_from_filename(self.request.get_local_filename())
        
        def _close(self):
            self._bm.close()
        
        def _get_data(self, index):
            if index != 0:
                raise IndexError('This format only supports singleton images.')
            return self._bm.get_image_data(), self._bm.get_meta_data()
        
        def _get_meta_data(self, index):
            if not (index is None or index == 0):
                raise IndexError()
            return self._bm.get_meta_data()
    
    # --
    
    class Writer(Format.Writer):
        
        def _open(self, flags=0):        
            self._flags = flags  # Store flags for later use
            self._bm = None
            self._is_set = False  # To prevent appending more than one image
            self._meta = {}
        
        def _close(self):
            # Set global meta data
            self._bm.set_meta_data(self._meta)
            # Write and close
            self._bm.save_to_filename(self.request.get_local_filename())
            self._bm.close()
        
        def _append_data(self, im, meta):    
            # Check if set
            if not self._is_set:
                self._is_set = True
            else:
                raise RuntimeError('Singleton image; '
                                   'can only append image data once.')
            # Pop unit dimension for grayscale images
            if im.ndim == 3 and im.shape[-1] == 1:
                im = im[:, :, 0]
            # Lazy instantaion of the bitmap, we need image data
            if self._bm is None:
                self._bm = fi.create_bitmap(self.request.filename, 
                                            self.format.fif, self._flags)
                self._bm.allocate(im)
            # Set data
            self._bm.set_image_data(im)
            # There is no distinction between global and per-image meta data 
            # for singleton images
            self._meta = meta  
        
        def _set_meta_data(self, meta):
            self._meta = meta


## Special plugins

# todo: there is also FIF_LOAD_NOPIXELS, 
# but perhaps that should be used with get_meta_data.

class FreeimageBmpFormat(FreeimageFormat):
    """ A BMP format based on the Freeimage library.
    
    This format supports grayscale, RGB and RGBA images.
    
    Parameters for saving
    ---------------------
    compression : bool
        Whether to compress the bitmap using RLE when saving. Default False.
        It seems this does not always work, but who cares, you should use
        PNG anyway.
    
    """

    class Writer(FreeimageFormat.Writer):
        def _open(self, flags=0, compression=False):
            # Build flags from kwargs
            flags = int(flags)
            if compression:
                flags |= IO_FLAGS.BMP_SAVE_RLE
            else:
                flags |= IO_FLAGS.BMP_DEFAULT
            # Act as usual, but with modified flags
            return FreeimageFormat.Writer._open(self, flags)
        
        def _append_data(self, im, meta):
            im = image_as_uint8(im)
            return FreeimageFormat.Writer._append_data(self, im, meta)


class FreeimagePngFormat(FreeimageFormat):
    """ A PNG format based on the Freeimage library.
    
    This format supports grayscale, RGB and RGBA images.
    
    Parameters for reading
    ----------------------
    ignoregamma : bool
        Avoid gamma correction. Default False.
    
    Parameters for saving
    ---------------------
    compression : {0, 1, 6, 9}
        The compression factor. Higher factors result in more
        compression at the cost of speed. Note that PNG compression is
        always lossless. Default 9.
    quantize : int
        If specified, turn the given RGB or RGBA image in a paletted image
        for more efficient storage. The value should be between 2 and 256.
        If the value of 0 the image is not quantized.
    interlaced : bool
        Save using Adam7 interlacing. Default False.
    """
    
    class Reader(FreeimageFormat.Reader):
        def _open(self, flags=0, ignoregamma=False):
            # Build flags from kwargs
            flags = int(flags)        
            if ignoregamma:
                flags |= IO_FLAGS.PNG_IGNOREGAMMA
            # Enter as usual, with modified flags
            return FreeimageFormat.Reader._open(self, flags)
    
    # -- 
    
    class Writer(FreeimageFormat.Writer):
        def _open(self, flags=0, compression=9, quantize=0, interlaced=False):
            compression_map = {0: IO_FLAGS.PNG_Z_NO_COMPRESSION,
                               1: IO_FLAGS.PNG_Z_BEST_SPEED,
                               6: IO_FLAGS.PNG_Z_DEFAULT_COMPRESSION,
                               9: IO_FLAGS.PNG_Z_BEST_COMPRESSION, }
            # Build flags from kwargs
            flags = int(flags)
            if interlaced:
                flags |= IO_FLAGS.PNG_INTERLACED
            try:
                flags |= compression_map[compression]
            except KeyError:
                raise ValueError('Png compression must be 0, 1, 6, or 9.')
            # Act as usual, but with modified flags
            return FreeimageFormat.Writer._open(self, flags)
        
        def _append_data(self, im, meta):
            im = image_as_uint8(im)
            FreeimageFormat.Writer._append_data(self, im, meta)
            # Quantize?
            q = int(self.request.kwargs.get('quantize', False))
            if not q:
                pass
            elif not (im.ndim == 3 and im.shape[-1] == 3):
                raise ValueError('Can only quantize RGB images')
            elif q < 2 or q > 256:
                raise ValueError('PNG quantize param must be 2..256')
            else:
                bm = self._bm.quantize(0, q)
                self._bm.close()
                self._bm = bm


class FreeimageJpegFormat(FreeimageFormat):
    """ A JPEG format based on the Freeimage library.
    
    This format supports grayscale and RGB images.
    
    Parameters for reading
    ----------------------
    exifrotate : bool
        Automatically rotate the image according to the exif flag.
        Default True. If 2 is given, do the rotation in Python instead
        of freeimage.
    quickread : bool
        Read the image more quickly, at the expense of quality. 
        Default False.
    
    Parameters for saving
    ---------------------
    quality : scalar
        The compression factor of the saved image (1..100), higher
        numbers result in higher quality but larger file size. Default 75.
    progressive : bool
        Save as a progressive JPEG file (e.g. for images on the web).
        Default False.
    optimize : bool
        On saving, compute optimal Huffman coding tables (can reduce a
        few percent of file size). Default False.
    baseline : bool
        Save basic JPEG, without metadata or any markers. Default False.
    
    """
    
    class Reader(FreeimageFormat.Reader):
        def _open(self, flags=0, exifrotate=True, quickread=False):
            # Build flags from kwargs
            flags = int(flags)        
            if exifrotate and exifrotate != 2:
                flags |= IO_FLAGS.JPEG_EXIFROTATE
            if not quickread:
                flags |= IO_FLAGS.JPEG_ACCURATE
            # Enter as usual, with modified flags
            return FreeimageFormat.Reader._open(self, flags)
        
        def _get_data(self, index):
            im, meta = FreeimageFormat.Reader._get_data(self, index)
            im = self._rotate(im, meta)
            return im, meta
        
        def _rotate(self, im, meta):
            """ Use Orientation information from EXIF meta data to 
            orient the image correctly. Freeimage is also supposed to
            support that, and I am pretty sure it once did, but now it
            does not, so let's just do it in Python.
            Edit: and now it works again, just leave in place as a fallback.
            """
            if self.request.kwargs.get('exifrotate', None) == 2:
                try:
                    ori = meta['EXIF_MAIN']['Orientation']
                except KeyError:  # pragma: no cover
                    pass  # Orientation not available
                else:  # pragma: no cover - we cannot touch all cases
                    # www.impulseadventure.com/photo/exif-orientation.html
                    if ori in [1, 2]:
                        pass
                    if ori in [3, 4]:
                        im = np.rot90(im, 2)
                    if ori in [5, 6]:
                        im = np.rot90(im, 3)
                    if ori in [7, 8]:
                        im = np.rot90(im)
                    if ori in [2, 4, 5, 7]:  # Flipped cases (rare)
                        im = np.fliplr(im)
            return im
    
    # --
        
    class Writer(FreeimageFormat.Writer):
        def _open(self, flags=0, quality=75, progressive=False, optimize=False,
                  baseline=False):
            # Test quality
            quality = int(quality)
            if quality < 1 or quality > 100:
                raise ValueError('JPEG quality should be between 1 and 100.')
            # Build flags from kwargs
            flags = int(flags)
            flags |= quality
            if progressive:
                flags |= IO_FLAGS.JPEG_PROGRESSIVE
            if optimize:
                flags |= IO_FLAGS.JPEG_OPTIMIZE
            if baseline:
                flags |= IO_FLAGS.JPEG_BASELINE
            # Act as usual, but with modified flags
            return FreeimageFormat.Writer._open(self, flags)
        
        def _append_data(self, im, meta):
            if im.ndim == 3 and im.shape[-1] == 4:
                raise IOError('JPEG does not support alpha channel.')
            im = image_as_uint8(im)
            return FreeimageFormat.Writer._append_data(self, im, meta)


## Create the formats

SPECIAL_CLASSES = {'jpeg': FreeimageJpegFormat,
                   'png': FreeimagePngFormat,
                   'bmp': FreeimageBmpFormat,
                   'gif': None,  # defined in freeimagemulti
                   'ico': None,  # defined in freeimagemulti
                   'mng': None,  # defined in freeimagemulti
                   }

# rename TIFF to make way for the tiffile plugin
NAME_MAP = {'TIFF': 'FI_TIFF'}

def create_freeimage_formats():
    
    # Freeimage available?
    if fi is None:  # pragma: no cover
        return 
    
    # Init
    lib = fi._lib
    
    # Create formats        
    for i in range(lib.FreeImage_GetFIFCount()):
        if lib.FreeImage_IsPluginEnabled(i):                
            # Get info
            name = lib.FreeImage_GetFormatFromFIF(i).decode('ascii')
            des = lib.FreeImage_GetFIFDescription(i).decode('ascii')
            ext = lib.FreeImage_GetFIFExtensionList(i).decode('ascii')
            name = NAME_MAP.get(name, name)
            # Get class for format
            FormatClass = SPECIAL_CLASSES.get(name.lower(), FreeimageFormat)
            if FormatClass:
                # Create Format and add
                format = FormatClass(name, des, ext, FormatClass._modes)
                format._fif = i
                formats.add_format(format)

create_freeimage_formats()
