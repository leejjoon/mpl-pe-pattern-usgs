import pkg_resources

import numpy as np
import json
from matplotlib.path import Path
from matplotlib.transforms import Bbox, TransformedBbox, Affine2D
import matplotlib.colors as mcolors
from matplotlib.backend_bases import RendererBase

from matplotlib.artist import Artist
from mpl_visual_context.patheffects_base  import AbstractPathEffect
from mpl_visual_context.transform_helper import TR


class FillPattern(AbstractPathEffect):
    """
    Fill the path with the given pattern.
    """

    def __init__(self, pattern, ax, color=None, alpha=None):
        """

        Keyword Arguments:

        color_cycle: list of colors. None has special meansing that it will be replaced by
                     the facecolor of the parent artist.
        alpha: alpha value for the pattern. If None, the alpha value from the parent artist
               will be used.
        """

        self.pb = PatternBox(pattern, extent=None, bbox=None, coords="figure pixels", axes=ax,
                             color=color)
        self._alpha = alpha

    def draw_path(self, renderer, gc, tpath, affine, rgbFace):

        bbox = tpath.get_extents(affine)
        self.pb.set_bbox(bbox)
        self.pb.set_clip_path(tpath, transform=affine)
        # FIXME This is inconsistent for now that alpha is from gc, fc is from rgbFace.
        self.pb.set_alpha(gc.get_alpha() if self._alpha is None else self._alpha)
        self.pb.set_none_color(rgbFace)
        self.pb.draw(renderer)
        # FIXME we may better recover the clip_path?

        renderer.draw_path(gc, tpath, affine, None)


class Pattern:
    def __init__(self, width, height, path, scale=1):
        self.width = width*scale
        self.height = height*scale
        self.path = type(path)(vertices=path.vertices*scale,
                               codes=path.codes)

    def fill(self, ax, color=None, alpha=None):

        return FillPattern(self, ax,
                           color=color, alpha=alpha)


class PatternBox(Artist):
    def _get_bbox_orig(self, extent, bbox):
        """
        Returns a bbox from the extent if extent is not None, otherwise
        returns a bbox itself. If both are None, return s unit bbox.
        """

        if bbox is not None:
            if extent is not None:
                raise ValueError("extent should be None if bbox is given")
            bbox_orig = bbox
        else:
            if extent is None:
                extent = [0, 0, 1, 1]
            bbox_orig = Bbox.from_extents(extent)

        return bbox_orig

    def set_bbox(self, bbox):
        self.bbox = bbox
        self.bbox_orig = self._get_bbox_orig(self.extent, bbox)

    def set_extent(self, extent):
        self.extent = extent
        self.bbox_orig = self._get_bbox_orig(extent, self.bbox)

    def __init__(self, pattern, extent=None, bbox=None, coords="data", axes=None,
                 color=None,
                 **artist_kw):
        super().__init__(**artist_kw)
        self.pattern = pattern
        self.extent = extent
        self.bbox = bbox
        self.bbox_orig = self._get_bbox_orig(extent, bbox)
        self.coords = coords
        self.axes = axes
        if axes is not None:
            self.set_clip_path(axes.patch)

        self.color = color
        self._none_color = None  # none color need to be set explicitly if
                                 # needed. It is set by FillPattern instance.

    def get_none_color(self):
        return self._none_color

    def set_none_color(self, rgb):
        self._none_color = rgb

    def draw(self, renderer):
        if not self.get_visible():
            return

        gc = renderer.new_gc()
        self._set_gc_clip(gc)
        gc.set_alpha(self.get_alpha())
        gc.set_url(self.get_url())

        tr = TR.get_xy_transform(renderer, self.coords, axes=self.axes)
        if callable(self.bbox_orig):
            bbox_orig = self.bbox_orig(renderer)
        else:
            bbox_orig = self.bbox_orig
        trbox = TransformedBbox(bbox_orig, tr)
        x0, y0 = trbox.x0, trbox.y0

        w = self.pattern.width
        h = self.pattern.height

        nx = int(trbox.width // w + 1)
        ny = int(trbox.height // h + 1)

        offsets = [(x0+w*ix, y0+h*iy) for ix in range(nx) for iy in range(ny)]

        for p, fc in [(self.pattern.path, self.color)]: # FIXME no need to use for loop

            if fc is None:
                fc = self.get_none_color()

            rgb = mcolors.to_rgb(fc)

            # FIXME: for now, the pattern will be drawn in the pixel
            # coordinate, so the pattern will be dependent of dpi used.

            _transforms = np.zeros((1, 3, 3))
            _transforms[0, 0, 0] = 1
            _transforms[0, 1, 1] = 1

            kl = (gc, Affine2D().frozen(), [p] * len(offsets),
                  _transforms, # all trans
                  np.array(offsets),
                  Affine2D().frozen(), # offset trans
                  np.array([rgb]), [], # face & edge
                  [], [], # lw, ls
                  [], [], #
                  None)
            RendererBase.draw_path_collection(renderer, *kl)
            # renderer.draw_path_collection(*kl) # FIXME: this fails with ValueError
            # (Expected 2-dimensional array, got 1). Could not figure out why.

        gc.restore()


class PatternUSGS:
    def __init__(self):

        fn_json = pkg_resources.resource_filename('mpl_pe_pattern_usgs',
                                                  'pattern_usgs.json')
        fn_npz = pkg_resources.resource_filename('mpl_pe_pattern_usgs',
                                                 'pattern_usgs_vertcies_codes.npz')

        self._j = json.load(open(fn_json))
        self._vc = np.load(fn_npz)

        roots = {}
        for j1 in self._j:
            roots[j1["root"]] = j1

        self.roots = roots

    def get(self, name, scale=1):
        "return an instance of pattern of a given name."
        j1 = self.roots[name]

        kc = f"{name}_codes"
        kv = f"{name}_vertices"

        codes = self._vc[kc]
        vertices = self._vc[kv]

        p = Path(vertices=vertices, codes=codes)

        w, h = j1["width"], j1["height"]

        return Pattern(w, h, p, scale=scale)


def test_plot():
    import matplotlib.pyplot as plt
    from matplotlib.text import TextPath
    from matplotlib.patches import PathPatch
    import mpl_visual_context.patheffects as pe

    pm = PatternUSGS()
    pattern = pm.get("603", scale=4)

    fig, ax = plt.subplots(num=1, clear=True)
    ax.set_aspect(1)
    p = TextPath((0, 0), "M", size=40)
    patch = PathPatch(p, ec="k", transform=ax.transData, fc="r")
    ax.add_patch(patch)

    patch.set_path_effects([# pe.FillOnly(),
                            pattern.fill(ax),
                            ])

    ax.set(xlim=(0, 40), ylim=(-5, 32))

    plt.show()


if __name__ == '__main__':
    test_plot()
