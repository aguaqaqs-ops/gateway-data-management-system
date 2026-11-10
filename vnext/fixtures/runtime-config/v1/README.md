# Runtime config format vectors

Both service adapters consume these exact inputs. The filled profile is a structural development example (N1/M24GiB/E32GiB/reserve8GiB, W=K=1); it has not passed host/mount/cgroup checks and is not a production capacity default. F must select an actually available CPU/host budget before running it. `expected_source` and all source directories are examples and must be filled for the actual host. Production uses bind mounts only. No service creates a missing source.

B owns strict JSON/schema/resource planning and logical identity. C/E/F own local root identity, symlink/mount checks, cgroups, initialization and lifecycle wiring.

`configuration-jcs.json` freezes complete UTF-8 canonical preimages and SHA256 for both adapters, including non-ASCII/astral source text, the I-JSON integer maximum, and JCS spellings for `2.0`, `1e-7`, and `-0.0`. The preimages use ASCII object keys sorted lexically, explicit RFC 8785 number spellings, and UTF-8 string values; they were authored independently of the two production serializers. Both adapters must match these same fixed bytes/digests. `invalid-configs.json` additionally rejects lone surrogates and Unicode noncharacters (including supplementary-plane endpoints), and integers beyond the safe I-JSON range.
