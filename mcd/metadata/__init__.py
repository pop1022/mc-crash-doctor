"""Mod metadata readers (ROADMAP 1D.1) and artifact classification (1D.4).

`mcd` diagnoses a crash from text alone; this package is the first thing that
looks *outside* the report -- at the jars, their filenames and their manifests --
to learn what their authors declared. It is imported only by tools and, later,
Pack Doctor; the diagnosis pipeline stays a pure function of the report text.

    from mcd.metadata.manifest import parse_jar
    for mod in parse_jar("mods/example-1.0.0.jar"):
        print(mod.modid, [d.modid for d in mod.negatives])

    from mcd.metadata.jars import classify_jar, partition_jars
    partition_jars(["guava-32.1.2-jre.jar", "Jade-1.20.1-Forge.jar"])
    # -> {"loader": [], "library": ["guava-32.1.2-jre.jar"],
    #     "mod": ["Jade-1.20.1-Forge.jar"], "unknown": []}

Two modules, two questions:

* `manifest` -- "what does this jar *declare*?" Reads `fabric.mod.json`,
  `quilt.mod.json`, `META-INF/mods.toml`, `META-INF/neoforge.mods.toml`.
  Authoritative, but only for jars you have on disk.
* `jars` -- "is this filename a mod, a library or the loader?" Works from a
  crash report alone, which is all we have for a harvested corpus, and is
  therefore *assumed* rather than declared: see its module docstring for what
  the `mod` verdict does and does not claim.
"""
