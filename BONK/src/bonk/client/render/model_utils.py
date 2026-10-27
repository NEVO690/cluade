"""Helpers for models imported from glTF files."""


def srgb_fix(np_):
    """Prepare an imported glTF model for this renderer.

    * glTF base colours are linear; Panda's default pipeline shows them too dark;
    * closed meshes are drawn single-sided so they do not self-shadow.
    """
    np_.setTwoSided(False, 1)
    for mat in np_.findAllMaterials():
        c = mat.getBaseColor() if mat.hasBaseColor() else mat.getDiffuse()

        def to_srgb(v):
            v = max(0.0, min(1.0, v))
            return 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055

        fixed = (to_srgb(c[0]), to_srgb(c[1]), to_srgb(c[2]), c[3])
        mat.setBaseColor(fixed)
        mat.setDiffuse(fixed)
        if mat.hasEmission():
            e = mat.getEmission()
            mat.setEmission((to_srgb(e[0]), to_srgb(e[1]), to_srgb(e[2]), 1))
    return np_
