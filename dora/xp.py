# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha1
import json
from pathlib import Path
import typing as tp

from .conf import DoraConfig
from .link import Link
from .utils import jsonable

from webcolors import CSS3_HEX_TO_NAMES, hex_to_rgb
from scipy.spatial import KDTree
import os

def convert_rgb_to_names(rgb_tuple):
    
    # a dictionary of all the hex and their respective names in css3
    css3_db = CSS3_HEX_TO_NAMES
    names = []
    rgb_values = []    
    for color_hex, color_name in css3_db.items():
        names.append(color_name)
        rgb_values.append(hex_to_rgb(color_hex))
    
    kdt_db = KDTree(rgb_values)    
    distance, index = kdt_db.query(rgb_tuple)

    return names[index]


def _get_sig_str(original_sig: str):
    # convert hash to colour + pokemon string
    colour_hex, poki_hex = original_sig[:6], original_sig[6:]

    rgb = tuple(int(colour_hex[i:i+2], 16) for i in (0, 2, 4))
    colour_str = convert_rgb_to_names(rgb)

    # Get the absolute path of the directory containing this script
    current_directory = os.path.dirname(os.path.abspath(__file__))

    # Construct the absolute path to the "pokemon" file
    pokemon_path = os.path.join(current_directory, 'pokemon.txt')

    with open(pokemon_path, 'r') as f:
        pokemon = f.readlines()

        poki_str = pokemon[int(poki_hex, 16)]

    return f'{colour_str}{poki_str[:-1]}' # only use pokimon

def _get_sig(delta: tp.List[tp.Any]) -> str:
    # Return signature from a jsonable content.
    sorted_delta = sorted(delta)
    original_sig = sha1(json.dumps(sorted_delta).encode('utf8')).hexdigest()[:8]
    return _get_sig_str(original_sig)


@dataclass(init=False)
class XP:
    """
    Represent a single experiment, i.e. a specific set of parameters
    that is linked to a unique signature.

    One XP can have multiple runs.
    """
    dora: DoraConfig
    cfg: tp.Any
    argv: tp.List[str]
    sig: str
    delta: tp.Optional[tp.List[tp.Tuple[str, tp.Any]]]
    link: Link = field(compare=False)

    def __init__(self, dora: DoraConfig, cfg: tp.Any, argv: tp.List[str],
                 delta: tp.Optional[tp.List[tp.Tuple[str, tp.Any]]] = None,
                 sig: tp.Optional[str] = None):
        self.dora = dora
        self.cfg = cfg
        self.argv = argv
        if delta is not None:
            delta = jsonable([(k, v) for k, v in delta if not dora.is_excluded(k)])
        self.delta = delta
        if sig is None:
            assert delta is not None
            sig = _get_sig(delta)
        self.sig = sig
        self.link = Link(self.folder / self.dora.history)

    @property
    def folder(self) -> Path:
        assert self.sig is not None
        return self.dora.dir / self.dora.xps / self.sig

    @property
    def code_folder(self) -> Path:
        if self.dora.git_save:
            return self.folder / 'code'
        else:
            return Path('.')

    @property
    def _xp_submitit(self) -> Path:
        return self.folder / self.dora.shep.submitit_folder

    @property
    def _latest_submitit(self) -> Path:
        return self.folder / self.dora.shep.latest_submitit

    @property
    def submitit(self) -> Path:
        if self._latest_submitit.exists():
            return self._latest_submitit
        else:
            return self._xp_submitit

    @property
    def rendezvous_file(self) -> Path:
        return self.folder / self.dora.rendezvous_file

    @property
    def history(self) -> Path:
        return self.folder / self.dora.history

    @property
    def _argv_cache(self) -> Path:
        return self.folder / ".argv.json"

    @property
    def _shared_folder(self) -> tp.Optional[Path]:
        if self.dora.shared is not None:
            return self.dora.shared / self.dora.xps / self.sig
        return None

    @property
    def _shared_argv_cache(self) -> tp.Optional[Path]:
        if self._shared_folder is not None:
            return self._shared_folder / ".argv.json"
        return None

    @contextmanager
    def enter(self, stack: bool = False):
        """Context manager, fake being in the XP for its duration.

        Set `stack=True` if you want to allow this to happen from within
        another experiment.

        ..Warning:: For hydra experiment, this will not convert any path
            automatically, or setup loggers etc.
        """
        with _context.enter_xp(self, stack):
            yield


class _Context:
    # Used to keep track of a running XP and be able to provide
    # it on demand with `get_xp`.
    def __init__(self) -> None:
        self._xps: tp.List[XP] = []

    @contextmanager
    def enter_xp(self, xp: XP, stack: bool = False):
        if self._xps and not stack:
            raise RuntimeError("Already in a xp.")
        self._xps.append(xp)
        try:
            yield
        finally:
            self._xps.pop(-1)


_context = _Context()


def get_xp() -> XP:
    """When running from within an XP, returns the XP object.
    Otherwise, raises RuntimeError.
    """
    if not _context._xps:
        raise RuntimeError("Not in a xp!")
    else:
        return _context._xps[-1]


def is_xp() -> bool:
    """Return True if running within an XP."""
    return bool(_context._xps)
