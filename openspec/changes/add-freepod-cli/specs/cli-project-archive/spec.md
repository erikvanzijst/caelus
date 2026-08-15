## Purpose

How a project directory becomes the archive the platform builds from: which files are
included, how the archive is laid out, and which limits the client is entitled to
enforce on its own.

## ADDED Requirements

### Requirement: The archive carries project files at its root

The archive SHALL contain the project's files at the archive root, with paths relative
to the project root and no enclosing top-level directory. It SHALL NOT contain absolute
paths.

The platform extracts the archive without stripping leading path components and detects
the project at the extraction root, so an enclosing directory would present as an
undetectable project rather than as a malformed archive.

#### Scenario: A file at the project root is at the archive root

- **WHEN** a project containing a manifest file at its root is packed
- **THEN** that file appears at the archive root, not nested under a directory

#### Scenario: No absolute paths are emitted

- **WHEN** any project is packed
- **THEN** every member path in the archive is relative

### Requirement: File selection follows a fixed precedence

The client SHALL select files by applying, in order:

1. **Hard excludes**, which SHALL always apply and SHALL NOT be overridable: the version
   control directory.
2. **Built-in default excludes**, which SHALL always apply: common dependency,
   build-output, cache, and editor-artifact directories and files.
3. **The project's version-control ignore files**, honored by default, with an explicit
   option to disable honoring them.
4. **A client-specific ignore file**, `.freepodignore`, applied last so that its
   negations can re-include anything except a hard exclude.

The project file `.freepod.json` SHALL be included in the archive.

#### Scenario: Version control data is never uploaded

- **WHEN** a project is packed, with or without a `.freepodignore` attempting to
  re-include it
- **THEN** the version control directory is absent from the archive

#### Scenario: Version-control ignores are honored by default

- **WHEN** a project's ignore file excludes a build output directory
- **THEN** that directory is absent from the archive

#### Scenario: Honoring version-control ignores can be disabled

- **WHEN** packing runs with honoring version-control ignores disabled
- **THEN** files excluded only by those ignore files are included

#### Scenario: The client ignore file has the final say

- **WHEN** `.freepodignore` re-includes a path that a default exclude or a
  version-control ignore had excluded
- **THEN** that path is present in the archive

### Requirement: Ignore matching follows gitignore semantics

Patterns in ignore files SHALL be interpreted with gitignore semantics: anchoring based
on whether a pattern contains a separator, directory-only patterns, recursive wildcards,
character classes, comments, and negation with last-match-wins.

A file beneath a directory excluded **by the project's own ignore files** SHALL NOT be
re-includable by a later negation, matching the behavior of version control, and the
client SHALL NOT descend into such a directory.

That rule SHALL NOT extend to a directory excluded only by a built-in default. The
defaults are a client invention with no version-control equivalent, and several of them
name the very directories the re-inclusion idiom below is written for; applying the
no-re-inclusion rule to them would make the documented escape hatch silently
inoperative. A directory excluded only by a built-in default SHALL therefore be
traversed when, and only when, the project negates a path beneath it.

A negation SHALL count for that purpose only when it **names** the path it re-includes —
that is, when it is anchored to a path beneath the directory. An unanchored negation,
which version-control semantics would match at any depth, SHALL NOT cause a
default-excluded directory to be traversed, because deciding otherwise would make a
single depth-independent pattern walk every dependency tree the defaults exist to skip.
The client SHALL document that an unanchored negation does not reach inside a
default-excluded directory, and that anchoring it is the remedy — this is the same
silently-inoperative failure the rule above exists to prevent, and it is invisible
without being stated.

Since no default has a version-control equivalent, this SHALL NOT weaken parity: on a
tree whose paths do not collide with a built-in default, the client and version control
SHALL select identically.

#### Scenario: A negation cannot reach inside a directory the project excluded

- **WHEN** a project whose own ignore file excludes a directory and then negates a file
  inside it is packed
- **THEN** that file is absent from the archive

#### Scenario: An anchored negation does reach inside a directory only a built-in default excluded

- **WHEN** a project negates a path that names a location beneath a directory only a
  built-in default excluded
- **THEN** the negated path is present in the archive
- **AND** nothing else beneath that directory is, at any depth

#### Scenario: Anchoring is required at each level it must reach

- **WHEN** a project's negation names a path beneath a default-excluded directory but
  becomes depth-independent partway down, such as by a recursive wildcard in the middle
- **THEN** it re-includes only at the levels it names, and the deeper ones stay absent
- **AND** naming the full path re-includes at that depth

#### Scenario: An unanchored negation does not force traversal

- **WHEN** a project's only negation matches by name at any depth rather than naming a
  path beneath a default-excluded directory
- **THEN** that directory is still not traversed and the file is absent
- **AND** the documented remedy is to anchor the negation to the path it re-includes

#### Scenario: Parity holds on trees that do not collide with the defaults

- **WHEN** a project whose paths match no built-in default is packed
- **THEN** the selected files are exactly those version control would track

#### Scenario: Excluding entries rather than the directory permits re-inclusion

- **WHEN** a project whose ignore file excludes a directory's entries and then negates
  one of them is packed
- **THEN** the negated file is present in the archive

#### Scenario: Excluded directories are not traversed

- **WHEN** a project containing a large excluded dependency directory is packed, and the
  project negates nothing beneath that directory
- **THEN** the client does not enumerate that directory's contents

### Requirement: Environment files are excluded only when conventionally uncommitted

The built-in default excludes SHALL cover the environment-file variants the ecosystem
conventionally keeps out of version control, and SHALL NOT exclude a plain `.env`.

A build runs on the platform, and front-end tooling commonly reads `.env` while
producing its distributable output, so dropping it would yield a silently misconfigured
build rather than an error. A `.env` that is genuinely secret is already excluded by
the project's version-control ignore file.

#### Scenario: A committed environment file reaches the build

- **WHEN** a project containing a committed `.env` is packed
- **THEN** that file is present in the archive

#### Scenario: Local environment overrides are excluded

- **WHEN** a project contains local environment override files
- **THEN** those files are absent from the archive

### Requirement: Members that cannot be extracted safely are excluded locally

The client SHALL omit entries the platform's extraction would refuse — sockets, FIFOs,
device nodes, and symbolic links resolving outside the project — and SHALL report each
omission with its path.

Left in the archive, such an entry fails the entire extraction; omitted here, it is a
single legible message.

#### Scenario: A symlink escaping the project is omitted and reported

- **WHEN** a project contains a symbolic link resolving outside the project root
- **THEN** the archive omits it and the client names the offending path

#### Scenario: Special files are omitted and reported

- **WHEN** a project contains a socket, FIFO, or device node
- **THEN** the archive omits it and the client names the offending path

### Requirement: Archive contents are deterministic for a given tree

For an unchanged tree, packing SHALL produce the same member ordering and the same
member metadata across runs. Entries SHALL be ordered by path, and ownership metadata
SHALL be normalized rather than reflecting the packing machine's accounts.

#### Scenario: Repacking an unchanged tree is reproducible

- **WHEN** the same unchanged project is packed twice
- **THEN** both archives list the same members in the same order

#### Scenario: Local account details do not leak

- **WHEN** any project is packed
- **THEN** member ownership metadata is normalized and carries no local user or group
  name

### Requirement: The archive is materialized before it is uploaded

The client SHALL produce the complete archive before beginning the upload, holding it in
memory when small and spilling to temporary storage when large. It SHALL NOT stream a
newly generated archive directly into the upload.

The upload is a signed form submission whose policy the object store evaluates against
the request, and a failed upload must be repeatable — re-packing a tree that may have
changed would produce a different archive.

#### Scenario: An interrupted upload is retried with the same bytes

- **WHEN** an upload fails partway and is retried
- **THEN** the retry sends the identical archive rather than re-packing the tree

#### Scenario: Temporary storage is released

- **WHEN** a deploy finishes, successfully or not
- **THEN** any temporary archive storage it created is removed

### Requirement: The client enforces only the size limit the platform reports

The client SHALL enforce exactly one limit of its own: the maximum archive size the
platform returns when it issues an upload slot. It SHALL compare the packed size against
that value before transferring anything, and SHALL report both the packed size and the
limit when refusing.

The client SHALL NOT enforce, hardcode, or approximate any other platform bound — in
particular the archive's entry count and its uncompressed size, which are configured on
the platform's build environment and are never reported to a client. A client carrying
its own copy of those numbers would drift when the platform retunes them, refusing
archives the platform would have accepted.

#### Scenario: An oversized archive is refused before transfer

- **WHEN** the packed archive exceeds the size the upload slot reports
- **THEN** the client refuses before sending any bytes
- **AND** reports both the packed size and the reported limit

#### Scenario: Platform-side limits are reported by the platform

- **WHEN** an archive exceeds a platform bound the client is not told about
- **THEN** the client does not pre-emptively refuse it
- **AND** the platform's explanation reaches the user through the streamed build output

#### Scenario: A raised platform limit takes effect without a client release

- **WHEN** the platform raises the maximum archive size
- **THEN** the client honors the new value from the next upload slot it is issued
