"""Synthetic FITS frames for the tests — headers only, 4x4 pixels."""

from pathlib import Path

import numpy as np
from astropy.io import fits


def write_frame(path: Path, imagetyp: str, date_obs: str,
                exptime: float, filt: str = '', obj: str = '',
                ccd_temp: float = -10.0, stackcnt: int | None = None,
                instrume: str = 'TestCam'):
    path.parent.mkdir(parents=True, exist_ok=True)
    hdu = fits.PrimaryHDU(np.zeros((4, 4), dtype=np.uint16))
    h = hdu.header
    h['IMAGETYP'] = imagetyp
    h['DATE-OBS'] = date_obs
    h['EXPTIME'] = exptime
    h['CCD-TEMP'] = ccd_temp
    h['INSTRUME'] = instrume
    if filt:
        h['FILTER'] = filt
    if obj:
        h['OBJECT'] = obj
    if stackcnt is not None:
        h['STACKCNT'] = stackcnt
    hdu.writeto(path, overwrite=True)
    return path


def build_dataset(root: Path) -> Path:
    """
    The case this fork exists for:

      lights   M42 / Ha / 300 s on two nights (2026-03-22 and 2026-03-23)
      flats    Ha, shot on 2026-03-25 only — days after the lights, so the
               per-session automatic match finds nothing for either night
      darks    300 s from a library night (2026-01-05)
      bias     from the same library night
    """
    root.mkdir(parents=True, exist_ok=True)

    for night, hour in (('2026-03-22', '22'), ('2026-03-23', '23')):
        for i in range(4):
            write_frame(root / 'lights' / f'light_{night}_{i}.fits',
                        'LIGHT', f'{night}T{hour}:0{i}:00',
                        300.0, filt='Ha', obj='M42')

    for i in range(5):
        write_frame(root / 'flats' / f'flat_{i}.fits',
                    'FLAT', f'2026-03-25T18:0{i}:00', 3.0, filt='Ha')

    for i in range(6):
        write_frame(root / 'darks' / f'dark_{i}.fits',
                    'DARK', f'2026-01-05T20:0{i}:00', 300.0)

    for i in range(6):
        write_frame(root / 'bias' / f'bias_{i}.fits',
                    'BIAS', f'2026-01-05T21:0{i}:00', 0.0)

    return root
