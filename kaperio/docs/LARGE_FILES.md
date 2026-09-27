# Large-file validation

The import cap remains 200 MiB (209,715,200 bytes), labelled 200MB in the UI.
This is a product limit, not a maximum supported by the underlying file formats.
ZIP expansion retains its separate 512 MiB / 10,000-entry limits.

## Changes in 0.4.0-alpha.4

- HTTP import hashes and stores chunks of at most 1 MiB, in a private temporary
  directory on the library filesystem. Only complete, inspected files are registered.
- HTTP downloads stream from disk instead of materializing the entire output.
- One import at a time limits combined transfer/inspection pressure. Overlapping
  requests receive 409; the existing browser import queue is already sequential.
- Stalled network transfers time out after 30 seconds without socket progress.
  Ordinary interruption, timeout, parse failure and failed registration clean up
  staging files. A forced process kill or power loss may leave a staging directory.
- Upload starts require input size plus 64 MiB free disk space. This is not a
  reservation or an estimate of the space needed by later conversion.
- PDF metadata inspection and validation use open file handles. Text export reuses
  one PDF reader and writes incrementally instead of rereading the PDF for every page.

These changes do not make every parser or converter constant-memory. PDF rewriting,
Office decryption and image-based Word export can retain substantial document data.

## Reproduction

The opt-in benchmark requires the development dependencies plus `psutil`. It writes
only synthetic fixtures, never personal documents, and does not invoke Hashcat.
Run from the `kaperio` directory on the target OS:

```powershell
.venv/Scripts/python.exe tests/large_documents.py --prepare --fixtures .test-data/large-documents
.venv/Scripts/python.exe tests/large_documents.py --fixtures .test-data/large-documents --executable dist/Loxmit/Loxmit.exe --report .test-data/large-results/after.json
```

For routine validation, omit `--fixtures` and `--prepare`:

```powershell
.venv/Scripts/python.exe tests/large_documents.py --executable dist/Loxmit/Loxmit.exe --report .test-results/large.json
```

This generates fixtures in a unique temporary directory and deletes them even
when a test fails. Only the small report remains. Explicit `--prepare --fixtures`
is reserved for intentionally retained cross-version comparisons.

Use the corresponding virtualenv Python and native executable paths on other OSes.
Run the same fixtures against the old executable for a baseline. Results identify
the executable and fixture SHA-256 values. Fixture encryption uses fresh randomness;
reuse the generated fixture set for comparisons rather than regenerating it.

The workloads contain 16 distinct 2048 x 2048 RGB images per document. PDF uses
AES-256, Office uses password-encrypted OOXML, and ZIP uses AES. Office plaintext
bytes, ZIP member hashes and PDF decoded image hashes are compared after unlock.
PDF also exercises image-PDF, image-based Word and text exports, including page/image
counts and a nonblank raster check. It does not exercise Office-to-PDF conversion.

Memory is sampled every 20 ms for the application and its child processes. RSS is
working-set memory on Windows; fixture generation, HTTP client, verification process
and OS file cache are excluded. Shorter peaks may be missed. A single local run is
not a hardware-independent guarantee or a statistical speed benchmark.

## Results

On 2026-09-25, Windows 11 x64 / 16 GiB RAM: all five fixtures passed against both
the alpha.3 baseline and alpha.4 build. Inputs ranged from 192.009 to 193.934 MiB.
All five passed import, known-password unlock, streamed client download and content
verification. The PDF additionally passed the three exports described above.
Local regression validation also passed 50 unit/HTTP tests, 20 frozen-executable
checks and 25 browser acceptance groups. These are separate from native hosted
Mac/Linux build checks and do not establish physical GPU performance.

Sampled peak process-tree RSS (MiB), in the same sequential workload:

| Operation | alpha.3 | alpha.4 |
|---|---:|---:|
| PDF import | 446.3 | 63.6 |
| PDF unlock | 638.7 | 254.8 |
| PDF download | 830.8 | 256.0 |
| PDF image-PDF export | 857.7 | 306.7 |
| PDF image-based Word export | 888.2 | 307.2 |
| PDF text export | 2490.8 | 451.2 |
| ZIP import | 254.0 | 63.6 |
| ZIP download | 255.3 | 63.8 |

The table shows total process RSS during each stage, not incremental allocation.
Memory retained from previous stages is included. This is one local run, not a
claim that every operation is faster: streamed downloads took longer in this run.
Office decryption still used approximately 618-622 MiB of private memory and did
not show a meaningful reduction. The underlying decryption library is unchanged.

Raw measurements and fixture/build identities:
[baseline](large-before-20260925.json), [after](large-after-20260925.json).
No personal documents or passwords are included in these records.

Decision: retain the 200 MiB limit. Exact-boundary HTTP tests also cover 200 MiB,
but those boundary fixtures stub document parsing; they are distinct from the
192-194 MiB end-to-end document tests. Larger caps, arbitrary high-compression
documents, physical Mac/Linux memory measurements and Office-to-PDF remain unproven.
