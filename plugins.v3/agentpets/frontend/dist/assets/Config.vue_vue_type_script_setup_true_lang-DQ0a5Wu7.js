import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { A as AGENT_HOST_KEY, H as HOST_UNSUPPORTED_MESSAGE } from './host-CDE6kQPw.js';
import { v as validatePack, B as BUILTIN_PACK_ID, b as builtinAsset, d as buildCodexPetPack } from './schema-C8VvGZ5b.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';
import { a as SCALE_RANGE, b as SPEED_RANGE, D as DEFAULT_SETTINGS, n as normalizeSettings, S as SETTINGS_EVENT } from './settings-_v7SC99m.js';

// DEFLATE is a complex format; to read this code, you should probably check the RFC first:
// https://tools.ietf.org/html/rfc1951
// You may also wish to take a look at the guide I made about this program:
// https://gist.github.com/101arrowz/253f31eb5abc3d9275ab943003ffecad
// Some of the following code is similar to that of UZIP.js:
// https://github.com/photopea/UZIP.js
// However, the vast majority of the codebase has diverged from UZIP.js to increase performance and reduce bundle size.
// Sometimes 0 will appear where -1 would be more appropriate. This is because using a uint
// is better for memory in most engines (I *think*).

// aliases for shorter compressed code (most minifers don't do this)
var u8 = Uint8Array, u16 = Uint16Array, i32 = Int32Array;
// fixed length extra bits
var fleb = new u8([0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0, /* unused */ 0, 0, /* impossible */ 0]);
// fixed distance extra bits
var fdeb = new u8([0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13, /* unused */ 0, 0]);
// code length index map
var clim = new u8([16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]);
// get base, reverse index map from extra bits
var freb = function (eb, start) {
    var b = new u16(31);
    for (var i = 0; i < 31; ++i) {
        b[i] = start += 1 << eb[i - 1];
    }
    // numbers here are at max 18 bits
    var r = new i32(b[30]);
    for (var i = 1; i < 30; ++i) {
        for (var j = b[i]; j < b[i + 1]; ++j) {
            r[j] = ((j - b[i]) << 5) | i;
        }
    }
    return { b: b, r: r };
};
var _a = freb(fleb, 2), fl = _a.b, revfl = _a.r;
// we can ignore the fact that the other numbers are wrong; they never happen anyway
fl[28] = 258, revfl[258] = 28;
var _b = freb(fdeb, 0), fd = _b.b;
// map of value to reverse (assuming 16 bits)
var rev = new u16(32768);
for (var i = 0; i < 32768; ++i) {
    // reverse table algorithm from SO
    var x = ((i & 0xAAAA) >> 1) | ((i & 0x5555) << 1);
    x = ((x & 0xCCCC) >> 2) | ((x & 0x3333) << 2);
    x = ((x & 0xF0F0) >> 4) | ((x & 0x0F0F) << 4);
    rev[i] = (((x & 0xFF00) >> 8) | ((x & 0x00FF) << 8)) >> 1;
}
// create huffman tree from u8 "map": index -> code length for code index
// mb (max bits) must be at most 15
// TODO: optimize/split up?
var hMap = (function (cd, mb, r) {
    var s = cd.length;
    // index
    var i = 0;
    // u16 "map": index -> # of codes with bit length = index
    var l = new u16(mb);
    // length of cd must be 288 (total # of codes)
    for (; i < s; ++i) {
        if (cd[i])
            ++l[cd[i] - 1];
    }
    // u16 "map": index -> minimum code for bit length = index
    var le = new u16(mb);
    for (i = 1; i < mb; ++i) {
        le[i] = (le[i - 1] + l[i - 1]) << 1;
    }
    var co;
    if (r) {
        // u16 "map": index -> number of actual bits, symbol for code
        co = new u16(1 << mb);
        // bits to remove for reverser
        var rvb = 15 - mb;
        for (i = 0; i < s; ++i) {
            // ignore 0 lengths
            if (cd[i]) {
                // num encoding both symbol and bits read
                var sv = (i << 4) | cd[i];
                // free bits
                var r_1 = mb - cd[i];
                // start value
                var v = le[cd[i] - 1]++ << r_1;
                // m is end value
                for (var m = v | ((1 << r_1) - 1); v <= m; ++v) {
                    // every 16 bit value starting with the code yields the same result
                    co[rev[v] >> rvb] = sv;
                }
            }
        }
    }
    else {
        co = new u16(s);
        for (i = 0; i < s; ++i) {
            if (cd[i]) {
                co[i] = rev[le[cd[i] - 1]++] >> (15 - cd[i]);
            }
        }
    }
    return co;
});
// fixed length tree
var flt = new u8(288);
for (var i = 0; i < 144; ++i)
    flt[i] = 8;
for (var i = 144; i < 256; ++i)
    flt[i] = 9;
for (var i = 256; i < 280; ++i)
    flt[i] = 7;
for (var i = 280; i < 288; ++i)
    flt[i] = 8;
// fixed distance tree
var fdt = new u8(32);
for (var i = 0; i < 32; ++i)
    fdt[i] = 5;
// fixed length map
var flrm = /*#__PURE__*/ hMap(flt, 9, 1);
// fixed distance map
var fdrm = /*#__PURE__*/ hMap(fdt, 5, 1);
// find max of array
var max = function (a) {
    var m = a[0];
    for (var i = 1; i < a.length; ++i) {
        if (a[i] > m)
            m = a[i];
    }
    return m;
};
// read d, starting at bit p and mask with m
var bits = function (d, p, m) {
    var o = (p / 8) | 0;
    return ((d[o] | (d[o + 1] << 8)) >> (p & 7)) & m;
};
// read d, starting at bit p continuing for at least 16 bits
var bits16 = function (d, p) {
    var o = (p / 8) | 0;
    return ((d[o] | (d[o + 1] << 8) | (d[o + 2] << 16)) >> (p & 7));
};
// get end of byte
var shft = function (p) { return ((p + 7) / 8) | 0; };
// typed array slice - allows garbage collector to free original reference,
// while being more compatible than .slice
var slc = function (v, s, e) {
    if (s == null || s < 0)
        s = 0;
    if (e == null || e > v.length)
        e = v.length;
    // can't use .constructor in case user-supplied
    return new u8(v.subarray(s, e));
};
// error codes
var ec = [
    'unexpected EOF',
    'invalid block type',
    'invalid length/literal',
    'invalid distance',
    'stream finished',
    'no stream handler',
    , // determined by compression function
    'no callback',
    'invalid UTF-8 data',
    'extra field too long',
    'date not in range 1980-2099',
    'filename too long',
    'stream finishing',
    'invalid zip data'
    // determined by unknown compression method
];
var err = function (ind, msg, nt) {
    var e = new Error(msg || ec[ind]);
    e.code = ind;
    if (Error.captureStackTrace)
        Error.captureStackTrace(e, err);
    if (!nt)
        throw e;
    return e;
};
// expands raw DEFLATE data
var inflt = function (dat, st, buf, dict) {
    // source length       dict length
    var sl = dat.length, dl = dict ? dict.length : 0;
    if (!sl || st.f && !st.l)
        return buf || new u8(0);
    var noBuf = !buf;
    // have to estimate size
    var resize = noBuf || st.i != 2;
    // no state
    var noSt = st.i;
    // Assumes roughly 33% compression ratio average
    if (noBuf)
        buf = new u8(sl * 3);
    // ensure buffer can fit at least l elements
    var cbuf = function (l) {
        var bl = buf.length;
        // need to increase size to fit
        if (l > bl) {
            // Double or set to necessary, whichever is greater
            var nbuf = new u8(Math.max(bl * 2, l));
            nbuf.set(buf);
            buf = nbuf;
        }
    };
    //  last chunk         bitpos           bytes
    var final = st.f || 0, pos = st.p || 0, bt = st.b || 0, lm = st.l, dm = st.d, lbt = st.m, dbt = st.n;
    // total bits
    var tbts = sl * 8;
    do {
        if (!lm) {
            // BFINAL - this is only 1 when last chunk is next
            final = bits(dat, pos, 1);
            // type: 0 = no compression, 1 = fixed huffman, 2 = dynamic huffman
            var type = bits(dat, pos + 1, 3);
            pos += 3;
            if (!type) {
                // go to end of byte boundary
                var s = shft(pos) + 4, l = dat[s - 4] | (dat[s - 3] << 8), t = s + l;
                if (t > sl) {
                    if (noSt)
                        err(0);
                    break;
                }
                // ensure size
                if (resize)
                    cbuf(bt + l);
                // Copy over uncompressed data
                buf.set(dat.subarray(s, t), bt);
                // Get new bitpos, update byte count
                st.b = bt += l, st.p = pos = t * 8, st.f = final;
                continue;
            }
            else if (type == 1)
                lm = flrm, dm = fdrm, lbt = 9, dbt = 5;
            else if (type == 2) {
                //  literal                            lengths
                var hLit = bits(dat, pos, 31) + 257, hcLen = bits(dat, pos + 10, 15) + 4;
                var tl = hLit + bits(dat, pos + 5, 31) + 1;
                pos += 14;
                // length+distance tree
                var ldt = new u8(tl);
                // code length tree
                var clt = new u8(19);
                for (var i = 0; i < hcLen; ++i) {
                    // use index map to get real code
                    clt[clim[i]] = bits(dat, pos + i * 3, 7);
                }
                pos += hcLen * 3;
                // code lengths bits
                var clb = max(clt), clbmsk = (1 << clb) - 1;
                // code lengths map
                var clm = hMap(clt, clb, 1);
                for (var i = 0; i < tl;) {
                    var r = clm[bits(dat, pos, clbmsk)];
                    // bits read
                    pos += r & 15;
                    // symbol
                    var s = r >> 4;
                    // code length to copy
                    if (s < 16) {
                        ldt[i++] = s;
                    }
                    else {
                        //  copy   count
                        var c = 0, n = 0;
                        if (s == 16)
                            n = 3 + bits(dat, pos, 3), pos += 2, c = ldt[i - 1];
                        else if (s == 17)
                            n = 3 + bits(dat, pos, 7), pos += 3;
                        else if (s == 18)
                            n = 11 + bits(dat, pos, 127), pos += 7;
                        while (n--)
                            ldt[i++] = c;
                    }
                }
                //    length tree                 distance tree
                var lt = ldt.subarray(0, hLit), dt = ldt.subarray(hLit);
                // max length bits
                lbt = max(lt);
                // max dist bits
                dbt = max(dt);
                lm = hMap(lt, lbt, 1);
                dm = hMap(dt, dbt, 1);
            }
            else
                err(1);
            if (pos > tbts) {
                if (noSt)
                    err(0);
                break;
            }
        }
        // Make sure the buffer can hold this + the largest possible addition
        // Maximum chunk size (practically, theoretically infinite) is 2^17
        if (resize)
            cbuf(bt + 131072);
        var lms = (1 << lbt) - 1, dms = (1 << dbt) - 1;
        var lpos = pos;
        for (;; lpos = pos) {
            // bits read, code
            var c = lm[bits16(dat, pos) & lms], sym = c >> 4;
            pos += c & 15;
            if (pos > tbts) {
                if (noSt)
                    err(0);
                break;
            }
            if (!c)
                err(2);
            if (sym < 256)
                buf[bt++] = sym;
            else if (sym == 256) {
                lpos = pos, lm = null;
                break;
            }
            else {
                var add = sym - 254;
                // no extra bits needed if less
                if (sym > 264) {
                    // index
                    var i = sym - 257, b = fleb[i];
                    add = bits(dat, pos, (1 << b) - 1) + fl[i];
                    pos += b;
                }
                // dist
                var d = dm[bits16(dat, pos) & dms], dsym = d >> 4;
                if (!d)
                    err(3);
                pos += d & 15;
                var dt = fd[dsym];
                if (dsym > 3) {
                    var b = fdeb[dsym];
                    dt += bits16(dat, pos) & (1 << b) - 1, pos += b;
                }
                if (pos > tbts) {
                    if (noSt)
                        err(0);
                    break;
                }
                if (resize)
                    cbuf(bt + 131072);
                var end = bt + add;
                if (bt < dt) {
                    var shift = dl - dt, dend = Math.min(dt, end);
                    if (shift + bt < 0)
                        err(3);
                    for (; bt < dend; ++bt)
                        buf[bt] = dict[shift + bt];
                }
                for (; bt < end; ++bt)
                    buf[bt] = buf[bt - dt];
            }
        }
        st.l = lm, st.p = lpos, st.b = bt, st.f = final;
        if (lm)
            final = 1, st.m = lbt, st.d = dm, st.n = dbt;
    } while (!final);
    // don't reallocate for streams or user buffers
    return bt != buf.length && noBuf ? slc(buf, 0, bt) : buf.subarray(0, bt);
};
// empty
var et = /*#__PURE__*/ new u8(0);
// read 2 bytes
var b2 = function (d, b) { return d[b] | (d[b + 1] << 8); };
// read 4 bytes
var b4 = function (d, b) { return (d[b] | (d[b + 1] << 8) | (d[b + 2] << 16) | (d[b + 3] << 24)) >>> 0; };
// read 8 bytes
var b8 = function (d, b) { return b4(d, b) + (b4(d, b + 4) * 4294967296); };
function inflateSync(data, opts) {
    return inflt(data, { i: 2 }, opts && opts.out, opts && opts.dictionary);
}
// text decoder
var td = typeof TextDecoder != 'undefined' && /*#__PURE__*/ new TextDecoder();
// text decoder stream
var tds = 0;
try {
    td.decode(et, { stream: true });
    tds = 1;
}
catch (e) { }
// decode UTF8
var dutf8 = function (d) {
    for (var r = '', i = 0;;) {
        var c = d[i++];
        var eb = (c > 127) + (c > 223) + (c > 239);
        if (i + eb > d.length)
            return { s: r, r: slc(d, i - 1) };
        if (!eb)
            r += String.fromCharCode(c);
        else if (eb == 3) {
            c = ((c & 15) << 18 | (d[i++] & 63) << 12 | (d[i++] & 63) << 6 | (d[i++] & 63)) - 65536,
                r += String.fromCharCode(55296 | (c >> 10), 56320 | (c & 1023));
        }
        else if (eb & 1)
            r += String.fromCharCode((c & 31) << 6 | (d[i++] & 63));
        else
            r += String.fromCharCode((c & 15) << 12 | (d[i++] & 63) << 6 | (d[i++] & 63));
    }
};
/**
 * Converts a Uint8Array to a string
 * @param dat The data to decode to string
 * @param latin1 Whether or not to interpret the data as Latin-1. This should
 *               not need to be true unless encoding to binary string.
 * @returns The original UTF-8/Latin-1 string
 */
function strFromU8(dat, latin1) {
    if (latin1) {
        var r = '';
        for (var i = 0; i < dat.length; i += 16384)
            r += String.fromCharCode.apply(null, dat.subarray(i, i + 16384));
        return r;
    }
    else if (td) {
        return td.decode(dat);
    }
    else {
        var _a = dutf8(dat), s = _a.s, r = _a.r;
        if (r.length)
            err(8);
        return s;
    }
}
// skip local zip header
var slzh = function (d, b) { return b + 30 + b2(d, b + 26) + b2(d, b + 28); };
// read zip header
var zh = function (d, b, z) {
    var fnl = b2(d, b + 28), efl = b2(d, b + 30), fn = strFromU8(d.subarray(b + 46, b + 46 + fnl), !(b2(d, b + 8) & 2048)), es = b + 46 + fnl;
    var _a = z64hs(d, es, efl, z, b4(d, b + 20), b4(d, b + 24), b4(d, b + 42)), sc = _a[0], su = _a[1], off = _a[2];
    return [b2(d, b + 10), sc, su, fn, es + efl + b2(d, b + 32), off];
};
// read zip64 header sizes
var z64hs = function (d, b, l, z, sc, su, off) {
    var nsc = sc == 4294967295, nsu = su == 4294967295, noff = off == 4294967295, e = b + l;
    var nf = nsc + nsu + noff;
    if (z && nf) {
        for (; b + 4 < e; b += 4 + b2(d, b + 2)) {
            if (b2(d, b) == 1) {
                return [
                    nsc ? b8(d, b + 4 + 8 * nsu) : sc,
                    nsu ? b8(d, b + 4) : su,
                    noff ? b8(d, b + 4 + 8 * (nsu + nsc)) : off,
                    1
                ];
            }
        }
        // z == 2 for unknown whether or not zip64
        if (z < 2)
            err(13);
    }
    return [sc, su, off, 0];
};
/**
 * Synchronously decompresses a ZIP archive. Prefer using `unzip` for better
 * performance with more than one file.
 * @param data The raw compressed ZIP file
 * @param opts The ZIP extraction options
 * @returns The decompressed files
 */
function unzipSync(data, opts) {
    var files = {};
    var e = data.length - 22;
    for (; b4(data, e) != 0x6054B50; --e) {
        if (!e || data.length - e > 65558)
            err(13);
    }
    var c = b2(data, e + 8);
    if (!c)
        return {};
    var o = b4(data, e + 16);
    var z = b4(data, e - 20) == 0x7064B50;
    if (z) {
        var ze = b4(data, e - 12);
        z = b4(data, ze) == 0x6064B50;
        if (z) {
            c = b4(data, ze + 32);
            o = b4(data, ze + 48);
        }
    }
    var fltr = opts && opts.filter;
    for (var i = 0; i < c; ++i) {
        var _a = zh(data, o, z), c_2 = _a[0], sc = _a[1], su = _a[2], fn = _a[3], no = _a[4], off = _a[5], b = slzh(data, off);
        o = no;
        if (!fltr || fltr({
            name: fn,
            size: sc,
            originalSize: su,
            compression: c_2
        })) {
            if (!c_2)
                files[fn] = slc(data, b, b + sc);
            else if (c_2 == 8)
                files[fn] = inflateSync(data.subarray(b, b + sc), { out: new u8(su) });
            else
                err(14, 'unknown compression type ' + c_2);
        }
    }
    return files;
}

const MAX_CODEX_PET_ARCHIVE_BYTES = 8 * 1024 * 1024;
const MAX_SPRITESHEET_BYTES = 4 * 1024 * 1024;
const MAX_MANIFEST_BYTES = 64 * 1024;
const MAX_ARCHIVE_ENTRIES = 256;
function isCodexPetArchive(file) {
  return file.name.toLowerCase().endsWith(".zip");
}
function normalizeEntryPath(path) {
  const normalized = path.replace(/\\/g, "/");
  if (!normalized || normalized.includes("\0") || normalized.startsWith("/") || /^[a-z]:/i.test(normalized)) {
    return null;
  }
  const parts = normalized.split("/");
  if (parts.some((part) => part === "..")) return null;
  return parts.filter((part) => part && part !== ".").join("/");
}
function resolveSpritesheetPath(manifestPath, path) {
  const normalized = path.trim().replace(/\\/g, "/");
  if (!normalized || normalized.includes("\0") || normalized.startsWith("/") || /^[a-z]:/i.test(normalized)) {
    throw new Error("pet.json 中的 spritesheetPath 必须是包内相对路径");
  }
  const parts = manifestPath.split("/").slice(0, -1);
  for (const part of normalized.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (!parts.length) throw new Error("pet.json 中的 spritesheetPath 不能越出压缩包");
      parts.pop();
    } else parts.push(part);
  }
  if (!parts.length) throw new Error("pet.json 中的 spritesheetPath 无效");
  return parts.join("/");
}
function manifestFromBytes(bytes) {
  let value;
  try {
    value = JSON.parse(strFromU8(bytes));
  } catch {
    throw new Error("pet.json 无法解析，请检查 JSON 格式");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("pet.json 顶层必须是对象");
  }
  const data = value;
  if (typeof data.spritesheetPath !== "string" || !data.spritesheetPath.trim()) {
    throw new Error("pet.json 缺少 spritesheetPath");
  }
  return {
    id: typeof data.id === "string" ? data.id : void 0,
    displayName: typeof data.displayName === "string" ? data.displayName : void 0,
    description: typeof data.description === "string" ? data.description : void 0,
    spritesheetPath: data.spritesheetPath
  };
}
function limitedUnzip(data, filter) {
  let entryCount = 0;
  let tooManyEntries = false;
  let files;
  try {
    files = unzipSync(data, {
      filter: (entry) => {
        entryCount += 1;
        if (entryCount > MAX_ARCHIVE_ENTRIES) {
          tooManyEntries = true;
          return false;
        }
        return filter(entry);
      }
    });
  } catch {
    throw new Error("Codex Pet ZIP 无法解压，可能已损坏或加密");
  }
  if (tooManyEntries) throw new Error(`压缩包文件数量不能超过 ${MAX_ARCHIVE_ENTRIES} 项`);
  return files;
}
function imageType(bytes) {
  if (bytes.length >= 8 && bytes[0] === 137 && bytes[1] === 80 && bytes[2] === 78 && bytes[3] === 71 && bytes[4] === 13 && bytes[5] === 10 && bytes[6] === 26 && bytes[7] === 10) {
    return { extension: "png", mime: "image/png" };
  }
  if (bytes.length >= 12 && String.fromCharCode(...bytes.subarray(0, 4)) === "RIFF" && String.fromCharCode(...bytes.subarray(8, 12)) === "WEBP") {
    return { extension: "webp", mime: "image/webp" };
  }
  throw new Error("Codex Pet 精灵图只支持 PNG 或 WebP");
}
function readFileBytes(file) {
  if (typeof file.arrayBuffer === "function") {
    return file.arrayBuffer().then((buffer) => new Uint8Array(buffer));
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (reader.result instanceof ArrayBuffer) resolve(new Uint8Array(reader.result));
      else reject(new Error("无法读取 Codex Pet 压缩包"));
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(file);
  });
}
async function extractCodexPetArchive(file) {
  if (!isCodexPetArchive(file)) throw new Error("压缩包文件名必须以 .zip 结尾");
  if (file.size > MAX_CODEX_PET_ARCHIVE_BYTES) throw new Error("Codex Pet 压缩包不能超过 8MB");
  let archive;
  try {
    archive = await readFileBytes(file);
  } catch {
    throw new Error("无法读取 Codex Pet 压缩包");
  }
  const manifestEntries = [];
  let oversizedManifest = false;
  const manifests = limitedUnzip(archive, (entry) => {
    const normalizedName = normalizeEntryPath(entry.name);
    if (!normalizedName || normalizedName.split("/").pop()?.toLowerCase() !== "pet.json") return false;
    manifestEntries.push({ name: entry.name, normalizedName });
    if (entry.originalSize > MAX_MANIFEST_BYTES) {
      oversizedManifest = true;
      return false;
    }
    return true;
  });
  if (manifestEntries.length > 1) throw new Error("压缩包包含多个 pet.json，无法确定导入对象");
  if (!manifestEntries.length) throw new Error("Codex Pet 压缩包中缺少 pet.json");
  if (oversizedManifest) throw new Error("pet.json 不能超过 64KB");
  const manifestEntry = manifestEntries[0];
  const manifestBytes = manifests[manifestEntry.name];
  if (!manifestBytes) throw new Error("无法读取 pet.json");
  const manifest = manifestFromBytes(manifestBytes);
  const spritesheetPath = resolveSpritesheetPath(manifestEntry.normalizedName, manifest.spritesheetPath);
  let matchingEntries = 0;
  let oversizedSpritesheet = false;
  let spritesheetEntryName = "";
  const spritesheets = limitedUnzip(archive, (entry) => {
    if (normalizeEntryPath(entry.name) !== spritesheetPath) return false;
    matchingEntries += 1;
    spritesheetEntryName = entry.name;
    if (entry.originalSize > MAX_SPRITESHEET_BYTES) {
      oversizedSpritesheet = true;
      return false;
    }
    return true;
  });
  if (matchingEntries > 1) throw new Error("压缩包中存在重复的精灵图路径");
  if (!matchingEntries) throw new Error("找不到 pet.json 指定的精灵图");
  if (oversizedSpritesheet) throw new Error("精灵图不能超过 4MB");
  const spritesheetBytes = spritesheets[spritesheetEntryName];
  if (!spritesheetBytes || spritesheetBytes.length > MAX_SPRITESHEET_BYTES) {
    throw new Error("精灵图内容无效或超过 4MB");
  }
  const type = imageType(spritesheetBytes);
  const filename = spritesheetPath.split("/").pop() || `spritesheet.${type.extension}`;
  const spritesheet = new File([spritesheetBytes], filename, { type: type.mime });
  return { manifest, spritesheet };
}

const {defineComponent:_defineComponent$2} = await importShared('vue');

const {createElementVNode:_createElementVNode$2,resolveComponent:_resolveComponent$2,openBlock:_openBlock$2,createBlock:_createBlock$1,createCommentVNode:_createCommentVNode$2,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock$1,withCtx:_withCtx$2,createVNode:_createVNode$2,toDisplayString:_toDisplayString$2,createTextVNode:_createTextVNode$2,createSlots:_createSlots,unref:_unref$2} = await importShared('vue');

const _hoisted_1$1 = { class: "agent-pet-sprites-config" };
const _hoisted_2$1 = { class: "d-flex align-center mt-3" };
const _hoisted_3$1 = { class: "text-caption text-medium-emphasis" };
const {computed,inject: inject$1,onMounted,ref: ref$1} = await importShared('vue');
const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
const _sfc_main$2 = /* @__PURE__ */ _defineComponent$2({
  __name: "PackManager",
  props: {
    api: { default: null },
    pluginId: { default: "" }
  },
  setup(__props) {
    const props = __props;
    const IMAGE_TYPES = ["image/png", "image/webp", "image/gif", "image/jpeg"];
    const EXAMPLE = JSON.stringify(
      {
        id: "my-pet",
        name: "我的形象",
        sheet: "https://example.com/sheet.png",
        grid: { cols: 4, rows: 2 },
        frames: { idle: 0, blink: 1, talk: 2, think: 3 },
        actions: {
          idle: { frames: ["idle", "idle", "blink"], frame_ms: 600, loop: true },
          thinking: { frames: ["think"], loop: true },
          speaking: ["talk", "idle"]
        },
        random_actions: ["wave"]
      },
      null,
      2
    );
    const toast = inject$1("moviepilot:toast", null);
    const confirm = inject$1("moviepilot:confirm", null);
    const instanceId = computed(() => props.pluginId || "AgentPets");
    const packs = ref$1([]);
    const loading = ref$1(false);
    const submitting = ref$1(false);
    const codexImporting = ref$1(false);
    const packText = ref$1("");
    const imageMode = ref$1("upload");
    const selectedFile = ref$1(null);
    const imageFile = ref$1(null);
    const fileModel = ref$1([]);
    const imageError = ref$1("");
    const importMessage = ref$1("");
    const importError = ref$1("");
    const serverError = ref$1("");
    const validation = computed(() => packText.value.trim() ? validatePack(packText.value) : null);
    const clientErrors = computed(() => {
      const errors = [...validation.value?.errors ?? []];
      if (imageMode.value === "url" && validation.value?.pack && !/^https?:\/\/\S+$/.test(validation.value.pack.sheet)) {
        errors.push("填写 URL 方式时，JSON 的 sheet 必须是 http(s) 图片地址");
      }
      return errors;
    });
    const canSubmit = computed(
      () => !!validation.value?.pack && !clientErrors.value.length && !submitting.value && (imageMode.value === "url" || !!imageFile.value && !imageError.value)
    );
    function previewSrc(pack) {
      if (pack.builtin) return builtinAsset("preview.png");
      return pack.preview;
    }
    function notify(kind, message) {
      toast?.[kind]?.(message);
    }
    async function refresh() {
      if (!props.api?.get) return;
      loading.value = true;
      try {
        const response = await props.api.get(`plugin/${instanceId.value}/packs`);
        if (response?.success && Array.isArray(response.data)) packs.value = response.data;
      } catch {
        console.warn("[AgentPets] packs unavailable");
      } finally {
        loading.value = false;
      }
    }
    function onImage(value) {
      const file = Array.isArray(value) ? value[0] ?? null : value ?? null;
      selectedFile.value = file;
      imageFile.value = file;
      imageError.value = "";
      importMessage.value = "";
      importError.value = "";
      serverError.value = "";
      if (!file) return;
      if (isCodexPetArchive(file)) {
        imageFile.value = null;
        if (file.size > MAX_CODEX_PET_ARCHIVE_BYTES) imageError.value = "Codex Pet 压缩包不能超过 8MB";
        return;
      }
      if (!IMAGE_TYPES.includes(file.type)) {
        imageFile.value = null;
        imageError.value = "只支持 PNG、WebP、GIF、JPEG 或 ZIP";
      } else if (file.size > MAX_IMAGE_BYTES) {
        imageFile.value = null;
        imageError.value = "精灵图不能超过 4MB";
      }
    }
    async function importCodexPet() {
      const file = selectedFile.value;
      if (!file || imageError.value) return;
      codexImporting.value = true;
      imageError.value = "";
      importMessage.value = "";
      importError.value = "";
      try {
        let image = file;
        let metadata;
        if (isCodexPetArchive(file)) {
          const extracted = await extractCodexPetArchive(file);
          image = extracted.spritesheet;
          metadata = extracted.manifest;
        } else if (file.type !== "image/png" && file.type !== "image/webp") {
          throw new Error("Codex Pet 导入只支持 PNG 或 WebP");
        }
        const bitmap = await createImageBitmap(image);
        const { width, height } = bitmap;
        bitmap.close();
        const result = buildCodexPetPack(image.name, width, height, metadata);
        imageMode.value = "upload";
        imageFile.value = image;
        packText.value = JSON.stringify(result.pack, null, 2);
        serverError.value = "";
        importMessage.value = (metadata ? "已从 Codex Pet 包读取精灵图，" : "已识别 Codex Pet ") + result.version + "，动作映射已生成";
      } catch (error) {
        importError.value = error instanceof Error ? error.message : "无法读取 Codex Pet 精灵图";
      } finally {
        codexImporting.value = false;
      }
    }
    function readDataUrl(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
    }
    async function addPack() {
      if (!canSubmit.value || !props.api?.post) return;
      submitting.value = true;
      serverError.value = "";
      try {
        const image = imageMode.value === "upload" && imageFile.value ? await readDataUrl(imageFile.value) : null;
        const response = await props.api.post(`plugin/${instanceId.value}/packs`, {
          pack: packText.value,
          image
        });
        if (!response?.success) {
          serverError.value = response?.message || "添加失败";
          return;
        }
        notify("success", `已添加素材包 ${response.data?.name ?? ""}`);
        packText.value = "";
        selectedFile.value = null;
        imageFile.value = null;
        fileModel.value = [];
        importMessage.value = "";
        importError.value = "";
        await refresh();
      } catch {
        serverError.value = "添加失败，请检查网络或稍后重试";
      } finally {
        submitting.value = false;
      }
    }
    async function removePack(pack) {
      if (!props.api?.post) return;
      const accepted = confirm ? await confirm({
        type: "warn",
        title: "删除素材包",
        content: `删除「${pack.name}」后，选择它的用户会回到内置机器人。`
      }) : window.confirm(`删除素材包「${pack.name}」？`);
      if (!accepted) return;
      const response = await props.api.post(`plugin/${instanceId.value}/packs/delete`, { id: pack.id });
      if (response?.success) {
        notify("success", `已删除素材包 ${pack.name}`);
        await refresh();
      } else notify("error", response?.message || "删除失败");
    }
    onMounted(refresh);
    return (_ctx, _cache) => {
      const _component_v_progress_linear = _resolveComponent$2("v-progress-linear");
      const _component_v_img = _resolveComponent$2("v-img");
      const _component_v_icon = _resolveComponent$2("v-icon");
      const _component_v_avatar = _resolveComponent$2("v-avatar");
      const _component_v_list_item_title = _resolveComponent$2("v-list-item-title");
      const _component_v_list_item_subtitle = _resolveComponent$2("v-list-item-subtitle");
      const _component_v_btn = _resolveComponent$2("v-btn");
      const _component_v_list_item = _resolveComponent$2("v-list-item");
      const _component_v_list = _resolveComponent$2("v-list");
      const _component_v_textarea = _resolveComponent$2("v-textarea");
      const _component_v_btn_toggle = _resolveComponent$2("v-btn-toggle");
      const _component_v_file_input = _resolveComponent$2("v-file-input");
      const _component_v_alert = _resolveComponent$2("v-alert");
      const _component_v_spacer = _resolveComponent$2("v-spacer");
      return _openBlock$2(), _createElementBlock$1("div", _hoisted_1$1, [
        _cache[7] || (_cache[7] = _createElementVNode$2("div", { class: "text-subtitle-2 mb-2" }, "已有素材包", -1)),
        loading.value ? (_openBlock$2(), _createBlock$1(_component_v_progress_linear, {
          key: 0,
          indeterminate: "",
          class: "mb-2"
        })) : _createCommentVNode$2("", true),
        _createVNode$2(_component_v_list, {
          density: "comfortable",
          class: "mb-6",
          border: "",
          rounded: ""
        }, {
          default: _withCtx$2(() => [
            (_openBlock$2(true), _createElementBlock$1(_Fragment, null, _renderList(packs.value, (pack) => {
              return _openBlock$2(), _createBlock$1(_component_v_list_item, {
                key: pack.id
              }, _createSlots({
                prepend: _withCtx$2(() => [
                  _createVNode$2(_component_v_avatar, {
                    rounded: "lg",
                    size: "48",
                    class: "agent-pet-sprites-config__thumb"
                  }, {
                    default: _withCtx$2(() => [
                      previewSrc(pack) ? (_openBlock$2(), _createBlock$1(_component_v_img, {
                        key: 0,
                        src: previewSrc(pack),
                        alt: pack.name
                      }, null, 8, ["src", "alt"])) : (_openBlock$2(), _createBlock$1(_component_v_icon, {
                        key: 1,
                        icon: "mdi-image-outline"
                      }))
                    ]),
                    _: 2
                  }, 1024)
                ]),
                default: _withCtx$2(() => [
                  _createVNode$2(_component_v_list_item_title, null, {
                    default: _withCtx$2(() => [
                      _createTextVNode$2(_toDisplayString$2(pack.name), 1)
                    ]),
                    _: 2
                  }, 1024),
                  _createVNode$2(_component_v_list_item_subtitle, null, {
                    default: _withCtx$2(() => [
                      _createTextVNode$2(_toDisplayString$2(pack.id) + " · " + _toDisplayString$2(pack.builtin ? "内置" : pack.source === "upload" ? "已上传" : "远程图片") + " · " + _toDisplayString$2(pack.mode === "stage" ? "全屏角色" : "入口外观") + " · " + _toDisplayString$2(pack.frame_count) + " 帧 · " + _toDisplayString$2(pack.action_count) + " 个动作 ", 1)
                    ]),
                    _: 2
                  }, 1024)
                ]),
                _: 2
              }, [
                !pack.builtin ? {
                  name: "append",
                  fn: _withCtx$2(() => [
                    _createVNode$2(_component_v_btn, {
                      icon: "mdi-delete-outline",
                      variant: "text",
                      "aria-label": `删除 ${pack.name}`,
                      onClick: ($event) => removePack(pack)
                    }, null, 8, ["aria-label", "onClick"])
                  ]),
                  key: "0"
                } : void 0
              ]), 1024);
            }), 128)),
            !packs.value.length && !loading.value ? (_openBlock$2(), _createBlock$1(_component_v_list_item, { key: 0 }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_list_item_title, { class: "text-medium-emphasis" }, {
                  default: _withCtx$2(() => [
                    _createTextVNode$2(_toDisplayString$2(props.api ? "暂无素材包" : "当前环境无法读取素材包"), 1)
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })) : _createCommentVNode$2("", true)
          ]),
          _: 1
        }),
        _cache[8] || (_cache[8] = _createElementVNode$2("div", { class: "text-subtitle-2 mb-2" }, "添加素材包", -1)),
        _createVNode$2(_component_v_textarea, {
          modelValue: packText.value,
          "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => packText.value = $event),
          label: "素材包 JSON",
          placeholder: _unref$2(EXAMPLE),
          rows: "8",
          "auto-grow": "",
          variant: "outlined",
          class: "agent-pet-sprites-config__json",
          "persistent-placeholder": "",
          "hide-details": "auto"
        }, null, 8, ["modelValue", "placeholder"]),
        _createVNode$2(_component_v_btn_toggle, {
          modelValue: imageMode.value,
          "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => imageMode.value = $event),
          mandatory: "",
          density: "comfortable",
          variant: "outlined",
          class: "my-3",
          divided: ""
        }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_btn, { value: "upload" }, {
              default: _withCtx$2(() => [..._cache[3] || (_cache[3] = [
                _createTextVNode$2("上传精灵图", -1)
              ])]),
              _: 1
            }),
            _createVNode$2(_component_v_btn, { value: "url" }, {
              default: _withCtx$2(() => [..._cache[4] || (_cache[4] = [
                _createTextVNode$2("使用 JSON 中的图片 URL", -1)
              ])]),
              _: 1
            })
          ]),
          _: 1
        }, 8, ["modelValue"]),
        imageMode.value === "upload" ? (_openBlock$2(), _createBlock$1(_component_v_file_input, {
          key: 1,
          modelValue: fileModel.value,
          "onUpdate:modelValue": [
            _cache[2] || (_cache[2] = ($event) => fileModel.value = $event),
            onImage
          ],
          label: "精灵图（不超过 4MB）或 ZIP（不超过 8MB）",
          accept: "image/png,image/webp,image/gif,image/jpeg,.zip",
          variant: "outlined",
          "prepend-icon": "mdi-image-outline",
          "error-messages": imageError.value ? [imageError.value] : [],
          "hide-details": "auto"
        }, null, 8, ["modelValue", "error-messages"])) : _createCommentVNode$2("", true),
        imageMode.value === "upload" ? (_openBlock$2(), _createBlock$1(_component_v_btn, {
          key: 2,
          class: "mt-2",
          color: "secondary",
          variant: "tonal",
          "prepend-icon": "mdi-file-import-outline",
          loading: codexImporting.value,
          disabled: !selectedFile.value || !!imageError.value || codexImporting.value,
          onClick: importCodexPet
        }, {
          default: _withCtx$2(() => [..._cache[5] || (_cache[5] = [
            _createTextVNode$2(" 从 Codex Pet 生成素材包 ", -1)
          ])]),
          _: 1
        }, 8, ["loading", "disabled"])) : _createCommentVNode$2("", true),
        importMessage.value ? (_openBlock$2(), _createBlock$1(_component_v_alert, {
          key: 3,
          type: "success",
          variant: "tonal",
          density: "compact",
          class: "mt-2"
        }, {
          default: _withCtx$2(() => [
            _createTextVNode$2(_toDisplayString$2(importMessage.value), 1)
          ]),
          _: 1
        })) : _createCommentVNode$2("", true),
        importError.value || clientErrors.value.length || serverError.value ? (_openBlock$2(), _createBlock$1(_component_v_alert, {
          key: 4,
          type: "error",
          variant: "tonal",
          density: "compact",
          class: "mt-3"
        }, {
          default: _withCtx$2(() => [
            (_openBlock$2(true), _createElementBlock$1(_Fragment, null, _renderList([...importError.value ? [importError.value] : [], ...clientErrors.value, ...serverError.value ? [serverError.value] : []], (error) => {
              return _openBlock$2(), _createElementBlock$1("div", { key: error }, _toDisplayString$2(error), 1);
            }), 128))
          ]),
          _: 1
        })) : _createCommentVNode$2("", true),
        _createElementVNode$2("div", _hoisted_2$1, [
          _createElementVNode$2("span", _hoisted_3$1, " 格式说明见插件 README；ID " + _toDisplayString$2(_unref$2(BUILTIN_PACK_ID)) + " 和 ying 留给内置形象。 ", 1),
          _createVNode$2(_component_v_spacer),
          _createVNode$2(_component_v_btn, {
            color: "primary",
            variant: "tonal",
            loading: submitting.value,
            disabled: !canSubmit.value,
            onClick: addPack
          }, {
            default: _withCtx$2(() => [..._cache[6] || (_cache[6] = [
              _createTextVNode$2(" 校验并添加 ", -1)
            ])]),
            _: 1
          }, 8, ["loading", "disabled"])
        ])
      ]);
    };
  }
});

const PackManager = /* @__PURE__ */ _export_sfc(_sfc_main$2, [["__scopeId", "data-v-8fb2c2be"]]);

const {defineComponent:_defineComponent$1} = await importShared('vue');

const {createElementVNode:_createElementVNode$1,unref:_unref$1,toDisplayString:_toDisplayString$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode$1,createTextVNode:_createTextVNode$1} = await importShared('vue');

const _hoisted_1 = { class: "agent-pets-stage-settings" };
const _hoisted_2 = { class: "agent-pets-stage-settings__value" };
const _hoisted_3 = { class: "agent-pets-stage-settings__value" };
const _hoisted_4 = { class: "d-flex align-center mt-3" };
const _hoisted_5 = {
  key: 0,
  class: "text-caption text-medium-emphasis"
};
const _sfc_main$1 = /* @__PURE__ */ _defineComponent$1({
  __name: "StageSettings",
  props: {
    modelValue: {},
    livePreview: { type: Boolean }
  },
  emits: ["update:modelValue"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const ROAM_OPTIONS = [
      { value: "surfaces", title: "站在页面元素上", hint: "落到卡片、对话框等元素的上边，元素移动或消失时跟着走或掉下来" },
      { value: "floor", title: "只在底边", hint: "始终站在屏幕底边" },
      { value: "free", title: "自由停放", hint: "没有重力，放在哪里停在哪里，空闲时在屏幕内慢慢游走" }
    ];
    function update(patch) {
      emit("update:modelValue", { ...props.modelValue, ...patch });
    }
    function reset() {
      emit("update:modelValue", { ...DEFAULT_SETTINGS });
    }
    return (_ctx, _cache) => {
      const _component_v_slider = _resolveComponent$1("v-slider");
      const _component_v_select = _resolveComponent$1("v-select");
      const _component_v_spacer = _resolveComponent$1("v-spacer");
      const _component_v_btn = _resolveComponent$1("v-btn");
      return _openBlock$1(), _createElementBlock("div", _hoisted_1, [
        _cache[4] || (_cache[4] = _createElementVNode$1("div", { class: "text-subtitle-2 mb-1" }, "角色大小", -1)),
        _createVNode$1(_component_v_slider, {
          "model-value": props.modelValue.scale,
          min: _unref$1(SCALE_RANGE)[0],
          max: _unref$1(SCALE_RANGE)[1],
          step: 0.05,
          color: "primary",
          "thumb-label": "",
          "hide-details": "",
          "aria-label": "角色大小",
          "onUpdate:modelValue": _cache[0] || (_cache[0] = (value) => update({ scale: Number(value) }))
        }, {
          append: _withCtx$1(() => [
            _createElementVNode$1("span", _hoisted_2, _toDisplayString$1(props.modelValue.scale.toFixed(2)) + "×", 1)
          ]),
          _: 1
        }, 8, ["model-value", "min", "max"]),
        _cache[5] || (_cache[5] = _createElementVNode$1("div", { class: "text-subtitle-2 mt-4 mb-1" }, "移动速度", -1)),
        _createVNode$1(_component_v_slider, {
          "model-value": props.modelValue.speed,
          min: _unref$1(SPEED_RANGE)[0],
          max: _unref$1(SPEED_RANGE)[1],
          step: 0.05,
          color: "primary",
          "thumb-label": "",
          "hide-details": "",
          "aria-label": "移动速度",
          "onUpdate:modelValue": _cache[1] || (_cache[1] = (value) => update({ speed: Number(value) }))
        }, {
          append: _withCtx$1(() => [
            _createElementVNode$1("span", _hoisted_3, _toDisplayString$1(props.modelValue.speed.toFixed(2)) + "×", 1)
          ]),
          _: 1
        }, 8, ["model-value", "min", "max"]),
        _createVNode$1(_component_v_select, {
          "model-value": props.modelValue.roam,
          items: ROAM_OPTIONS,
          "item-title": "title",
          "item-value": "value",
          label: "活动范围",
          variant: "outlined",
          density: "comfortable",
          class: "mt-5",
          hint: ROAM_OPTIONS.find((option) => option.value === props.modelValue.roam)?.hint,
          "persistent-hint": "",
          "onUpdate:modelValue": _cache[2] || (_cache[2] = (value) => update({ roam: value }))
        }, null, 8, ["model-value", "hint"]),
        _createElementVNode$1("div", _hoisted_4, [
          props.livePreview ? (_openBlock$1(), _createElementBlock("span", _hoisted_5, " 调整时页面上正在运行的小映或 Codex Pet 会实时变化，保存后对所有用户生效。 ")) : _createCommentVNode$1("", true),
          _createVNode$1(_component_v_spacer),
          _createVNode$1(_component_v_btn, {
            variant: "text",
            size: "small",
            onClick: reset
          }, {
            default: _withCtx$1(() => [..._cache[3] || (_cache[3] = [
              _createTextVNode$1("恢复默认", -1)
            ])]),
            _: 1
          })
        ])
      ]);
    };
  }
});

const StageSettings = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-a238247d"]]);

const {defineComponent:_defineComponent} = await importShared('vue');

const {unref:_unref,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createVNode:_createVNode,createElementVNode:_createElementVNode} = await importShared('vue');

const {inject,onBeforeUnmount,ref,watch} = await importShared('vue');
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Config",
  props: {
    initialConfig: { default: null },
    api: { default: null },
    pluginId: { default: "" }
  },
  emits: ["save", "close"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const agent = inject(AGENT_HOST_KEY, null);
    const saved = normalizeSettings(props.initialConfig);
    const enabled = ref(Boolean(props.initialConfig?.enabled));
    const stage = ref({ ...saved });
    let committed = false;
    watch(stage, (value) => agent?.emit?.(SETTINGS_EVENT, { ...value }), { deep: true });
    function save() {
      committed = true;
      emit("save", { enabled: enabled.value, ...normalizeSettings(stage.value) });
    }
    onBeforeUnmount(() => {
      if (!committed) agent?.emit?.(SETTINGS_EVENT, { ...saved });
    });
    return (_ctx, _cache) => {
      const _component_v_alert = _resolveComponent("v-alert");
      const _component_v_switch = _resolveComponent("v-switch");
      const _component_v_divider = _resolveComponent("v-divider");
      const _component_v_card_text = _resolveComponent("v-card-text");
      const _component_v_spacer = _resolveComponent("v-spacer");
      const _component_v_btn = _resolveComponent("v-btn");
      const _component_v_card_actions = _resolveComponent("v-card-actions");
      const _component_v_card = _resolveComponent("v-card");
      return _openBlock(), _createBlock(_component_v_card, {
        flat: "",
        class: "agent-pets-config"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_card_text, null, {
            default: _withCtx(() => [
              !_unref(agent) ? (_openBlock(), _createBlock(_component_v_alert, {
                key: 0,
                type: "warning",
                variant: "tonal",
                density: "compact",
                class: "mb-4"
              }, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(_unref(HOST_UNSUPPORTED_MESSAGE)), 1)
                ]),
                _: 1
              })) : _createCommentVNode("", true),
              _createVNode(_component_v_switch, {
                modelValue: enabled.value,
                "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => enabled.value = $event),
                label: "启用插件",
                color: "primary",
                "hide-details": "",
                class: "mb-2"
              }, null, 8, ["modelValue"]),
              _cache[3] || (_cache[3] = _createElementVNode("div", { class: "text-caption text-medium-emphasis mb-6" }, " 启用后，小映和每个素材包都会出现在个人设置的「助手形象」里，由用户自行选择。 ", -1)),
              _cache[4] || (_cache[4] = _createElementVNode("div", { class: "text-subtitle-1 mb-1" }, "全屏角色（小映与 Codex Pet）", -1)),
              _cache[5] || (_cache[5] = _createElementVNode("div", { class: "text-caption text-medium-emphasis mb-4" }, " 小映与导入的 Codex Pet 共用以下设置，可拖拽、站在页面元素上、散步和探头。 ", -1)),
              _createVNode(StageSettings, {
                modelValue: stage.value,
                "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => stage.value = $event),
                "live-preview": !!_unref(agent)
              }, null, 8, ["modelValue", "live-preview"]),
              _createVNode(_component_v_divider, { class: "my-6" }),
              _cache[6] || (_cache[6] = _createElementVNode("div", { class: "text-subtitle-1 mb-1" }, "素材包", -1)),
              _cache[7] || (_cache[7] = _createElementVNode("div", { class: "text-caption text-medium-emphasis mb-4" }, " Codex Pet 可在整个页面上活动；普通素材包替换右下角助手入口的画面。每个素材包都是一个可选形象。 ", -1)),
              _createVNode(PackManager, {
                api: props.api,
                "plugin-id": props.pluginId
              }, null, 8, ["api", "plugin-id"])
            ]),
            _: 1
          }),
          _createVNode(_component_v_card_actions, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_spacer),
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: _cache[2] || (_cache[2] = ($event) => emit("close"))
              }, {
                default: _withCtx(() => [..._cache[8] || (_cache[8] = [
                  _createTextVNode("关闭", -1)
                ])]),
                _: 1
              }),
              _createVNode(_component_v_btn, {
                color: "primary",
                variant: "flat",
                onClick: save
              }, {
                default: _withCtx(() => [..._cache[9] || (_cache[9] = [
                  _createTextVNode("保存", -1)
                ])]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      });
    };
  }
});

export { _sfc_main as _ };
