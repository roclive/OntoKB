# npocut in OntoKB

- Upstream: https://github.com/roclive/npocut
- Revision: `178e84e597db99a5377650c3164794ddb1205584`
- License: MIT; see [npocut/LICENSE](npocut/LICENSE).
- The `npocut/` directory is a complete, unmodified copy of this revision,
  including its `SKILL.md`, Python tools, examples, and optional standalone UI.

OntoKB's Codex media harness explicitly loads this skill. The local tool directory
is `third_party/npocut`, overriding the original author's macOS paths in the
upstream skill. Registered OntoKB tools execute the workflow on behalf of Codex;
the media agent does not need general shell or filesystem access.

Both media modes persist `clip_plan.csv` before cutting. The adapter
`src/ontokb/media_npocut.py` executes upstream `srt_slice.py` to generate
`highlight.source.srt` from that plan and retains `highlight.zh.srt` after Chinese
caption alignment. The files stay with the media in ignored `data/media/`.
OntoKB handles source acquisition, duration budgets, screenshot/audio encoding,
Chinese translation, and summary synchronization in its existing Python pipeline.
The upstream standalone Web UI is included for reference and is not launched by
OntoKB's integrated reading UI.

The same revision was installed locally with the standard skill-installer under
`~/.codex/skills/npocut`; its machine-local project paths are adjusted to this
checkout. The project copy remains portable and unchanged.
