# AgentPets asset conversion

`convert_agentmascot.py` reads statically extracted JSON data. It never executes
the source archive's runtime. Install the repository's locked frontend
dependencies through the normal authorized setup before using the converter;
Node.js and `plugins.v3/agentpets/frontend/node_modules/prettier` must exist.
The converter does not install tools or access the network.

```text
python scripts/agentpets/convert_agentmascot.py extracted-data.json output/packs --archive-sha256 <sha256>
```

Use a new output directory. Existing pack directories are not overwritten.
Both `pack.json` and `provenance.json` use the frontend Prettier configuration
and UTF-8 without BOM with LF endings, including on Windows. Check the generated
JSON, image hashes and source archive hash before replacing committed assets.
