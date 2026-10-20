import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { u as unwrap, A as AGENT_HOST_KEY, b as builtinAvatar, H as HOST_UNSUPPORTED_MESSAGE, l as loadEditor, p as prepareEnabledConfig } from './host-KC_Y5wME.js';
import { v as validatePack, k as framePosition, e as sameCalibration, P as PACK_UPDATED_EVENT, _ as _export_sfc, n as buildCodexPetPack } from './_plugin-vue_export-helper-DHgn0gTZ.js';

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
var _b = freb(fdeb, 0), fd = _b.b, revfd = _b.r;
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
var flm = /*#__PURE__*/ hMap(flt, 9, 0), flrm = /*#__PURE__*/ hMap(flt, 9, 1);
// fixed distance map
var fdm = /*#__PURE__*/ hMap(fdt, 5, 0), fdrm = /*#__PURE__*/ hMap(fdt, 5, 1);
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
// starting at p, write the minimum number of bits that can hold v to d
var wbits = function (d, p, v) {
    v <<= p & 7;
    var o = (p / 8) | 0;
    d[o] |= v;
    d[o + 1] |= v >> 8;
};
// starting at p, write the minimum number of bits (>8) that can hold v to d
var wbits16 = function (d, p, v) {
    v <<= p & 7;
    var o = (p / 8) | 0;
    d[o] |= v;
    d[o + 1] |= v >> 8;
    d[o + 2] |= v >> 16;
};
// creates code lengths from a frequency table
var hTree = function (d, mb) {
    // Need extra info to make a tree
    var t = [];
    for (var i = 0; i < d.length; ++i) {
        if (d[i])
            t.push({ s: i, f: d[i] });
    }
    var s = t.length;
    var t2 = t.slice();
    if (!s)
        return { t: et, l: 0 };
    if (s == 1) {
        var v = new u8(t[0].s + 1);
        v[t[0].s] = 1;
        return { t: v, l: 1 };
    }
    t.sort(function (a, b) { return a.f - b.f; });
    // after i2 reaches last ind, will be stopped
    // freq must be greater than largest possible number of symbols
    t.push({ s: -1, f: 25001 });
    var l = t[0], r = t[1], i0 = 0, i1 = 1, i2 = 2;
    t[0] = { s: -1, f: l.f + r.f, l: l, r: r };
    // efficient algorithm from UZIP.js
    // i0 is lookbehind, i2 is lookahead - after processing two low-freq
    // symbols that combined have high freq, will start processing i2 (high-freq,
    // non-composite) symbols instead
    // see https://reddit.com/r/photopea/comments/ikekht/uzipjs_questions/
    while (i1 != s - 1) {
        l = t[t[i0].f < t[i2].f ? i0++ : i2++];
        r = t[i0 != i1 && t[i0].f < t[i2].f ? i0++ : i2++];
        t[i1++] = { s: -1, f: l.f + r.f, l: l, r: r };
    }
    var maxSym = t2[0].s;
    for (var i = 1; i < s; ++i) {
        if (t2[i].s > maxSym)
            maxSym = t2[i].s;
    }
    // code lengths
    var tr = new u16(maxSym + 1);
    // max bits in tree
    var mbt = ln(t[i1 - 1], tr, 0);
    if (mbt > mb) {
        // more algorithms from UZIP.js
        // TODO: find out how this code works (debt)
        //  ind    debt
        var i = 0, dt = 0;
        //    left            cost
        var lft = mbt - mb, cst = 1 << lft;
        t2.sort(function (a, b) { return tr[b.s] - tr[a.s] || a.f - b.f; });
        for (; i < s; ++i) {
            var i2_1 = t2[i].s;
            if (tr[i2_1] > mb) {
                dt += cst - (1 << (mbt - tr[i2_1]));
                tr[i2_1] = mb;
            }
            else
                break;
        }
        dt >>= lft;
        while (dt > 0) {
            var i2_2 = t2[i].s;
            if (tr[i2_2] < mb)
                dt -= 1 << (mb - tr[i2_2]++ - 1);
            else
                ++i;
        }
        for (; i >= 0 && dt; --i) {
            var i2_3 = t2[i].s;
            if (tr[i2_3] == mb) {
                --tr[i2_3];
                ++dt;
            }
        }
        mbt = mb;
    }
    return { t: new u8(tr), l: mbt };
};
// get the max length and assign length codes
var ln = function (n, l, d) {
    return n.s == -1
        ? Math.max(ln(n.l, l, d + 1), ln(n.r, l, d + 1))
        : (l[n.s] = d);
};
// length codes generation
var lc = function (c) {
    var s = c.length;
    // Note that the semicolon was intentional
    while (s && !c[--s])
        ;
    var cl = new u16(++s);
    //  ind      num         streak
    var cli = 0, cln = c[0], cls = 1;
    var w = function (v) { cl[cli++] = v; };
    for (var i = 1; i <= s; ++i) {
        if (c[i] == cln && i != s)
            ++cls;
        else {
            if (!cln && cls > 2) {
                for (; cls > 138; cls -= 138)
                    w(32754);
                if (cls > 2) {
                    w(cls > 10 ? ((cls - 11) << 5) | 28690 : ((cls - 3) << 5) | 12305);
                    cls = 0;
                }
            }
            else if (cls > 3) {
                w(cln), --cls;
                for (; cls > 6; cls -= 6)
                    w(8304);
                if (cls > 2)
                    w(((cls - 3) << 5) | 8208), cls = 0;
            }
            while (cls--)
                w(cln);
            cls = 1;
            cln = c[i];
        }
    }
    return { c: cl.subarray(0, cli), n: s };
};
// calculate the length of output from tree, code lengths
var clen = function (cf, cl) {
    var l = 0;
    for (var i = 0; i < cl.length; ++i)
        l += cf[i] * cl[i];
    return l;
};
// writes a fixed block
// returns the new bit pos
var wfblk = function (out, pos, dat) {
    // no need to write 00 as type: TypedArray defaults to 0
    var s = dat.length;
    var o = shft(pos + 2);
    out[o] = s & 255;
    out[o + 1] = s >> 8;
    out[o + 2] = out[o] ^ 255;
    out[o + 3] = out[o + 1] ^ 255;
    for (var i = 0; i < s; ++i)
        out[o + i + 4] = dat[i];
    return (o + 4 + s) * 8;
};
// writes a block
var wblk = function (dat, out, final, syms, lf, df, eb, li, bs, bl, p) {
    wbits(out, p++, final);
    ++lf[256];
    var _a = hTree(lf, 15), dlt = _a.t, mlb = _a.l;
    var _b = hTree(df, 15), ddt = _b.t, mdb = _b.l;
    var _c = lc(dlt), lclt = _c.c, nlc = _c.n;
    var _d = lc(ddt), lcdt = _d.c, ndc = _d.n;
    var lcfreq = new u16(19);
    for (var i = 0; i < lclt.length; ++i)
        ++lcfreq[lclt[i] & 31];
    for (var i = 0; i < lcdt.length; ++i)
        ++lcfreq[lcdt[i] & 31];
    var _e = hTree(lcfreq, 7), lct = _e.t, mlcb = _e.l;
    var nlcc = 19;
    for (; nlcc > 4 && !lct[clim[nlcc - 1]]; --nlcc)
        ;
    var flen = (bl + 5) << 3;
    var ftlen = clen(lf, flt) + clen(df, fdt) + eb;
    var dtlen = clen(lf, dlt) + clen(df, ddt) + eb + 14 + 3 * nlcc + clen(lcfreq, lct) + 2 * lcfreq[16] + 3 * lcfreq[17] + 7 * lcfreq[18];
    if (bs >= 0 && flen <= ftlen && flen <= dtlen)
        return wfblk(out, p, dat.subarray(bs, bs + bl));
    var lm, ll, dm, dl;
    wbits(out, p, 1 + (dtlen < ftlen)), p += 2;
    if (dtlen < ftlen) {
        lm = hMap(dlt, mlb, 0), ll = dlt, dm = hMap(ddt, mdb, 0), dl = ddt;
        var llm = hMap(lct, mlcb, 0);
        wbits(out, p, nlc - 257);
        wbits(out, p + 5, ndc - 1);
        wbits(out, p + 10, nlcc - 4);
        p += 14;
        for (var i = 0; i < nlcc; ++i)
            wbits(out, p + 3 * i, lct[clim[i]]);
        p += 3 * nlcc;
        var lcts = [lclt, lcdt];
        for (var it = 0; it < 2; ++it) {
            var clct = lcts[it];
            for (var i = 0; i < clct.length; ++i) {
                var len = clct[i] & 31;
                wbits(out, p, llm[len]), p += lct[len];
                if (len > 15)
                    wbits(out, p, (clct[i] >> 5) & 127), p += clct[i] >> 12;
            }
        }
    }
    else {
        lm = flm, ll = flt, dm = fdm, dl = fdt;
    }
    for (var i = 0; i < li; ++i) {
        var sym = syms[i];
        if (sym > 255) {
            var len = (sym >> 18) & 31;
            wbits16(out, p, lm[len + 257]), p += ll[len + 257];
            if (len > 7)
                wbits(out, p, (sym >> 23) & 31), p += fleb[len];
            var dst = sym & 31;
            wbits16(out, p, dm[dst]), p += dl[dst];
            if (dst > 3)
                wbits16(out, p, (sym >> 5) & 8191), p += fdeb[dst];
        }
        else {
            wbits16(out, p, lm[sym]), p += ll[sym];
        }
    }
    wbits16(out, p, lm[256]);
    return p + ll[256];
};
// deflate options (nice << 13) | chain
var deo = /*#__PURE__*/ new i32([65540, 131080, 131088, 131104, 262176, 1048704, 1048832, 2114560, 2117632]);
// empty
var et = /*#__PURE__*/ new u8(0);
// compresses data into a raw DEFLATE buffer
var dflt = function (dat, lvl, plvl, pre, post, st) {
    var s = st.z || dat.length;
    var o = new u8(pre + s + 5 * (1 + Math.ceil(s / 7000)) + post);
    // writing to this writes to the output buffer
    var w = o.subarray(pre, o.length - post);
    var lst = st.l;
    var pos = (st.r || 0) & 7;
    if (lvl) {
        if (pos)
            w[0] = st.r >> 3;
        var opt = deo[lvl - 1];
        var n = opt >> 13, c = opt & 8191;
        var msk_1 = (1 << plvl) - 1;
        //    prev 2-byte val map    curr 2-byte val map
        var prev = st.p || new u16(32768), head = st.h || new u16(msk_1 + 1);
        var bs1_1 = Math.ceil(plvl / 3), bs2_1 = 2 * bs1_1;
        var hsh = function (i) { return (dat[i] ^ (dat[i + 1] << bs1_1) ^ (dat[i + 2] << bs2_1)) & msk_1; };
        // 24576 is an arbitrary number of maximum symbols per block
        // 424 buffer for last block
        var syms = new i32(25000);
        // length/literal freq   distance freq
        var lf = new u16(288), df = new u16(32);
        //  l/lcnt  exbits  index          l/lind  waitdx          blkpos
        var lc_1 = 0, eb = 0, i = st.i || 0, li = 0, wi = st.w || 0, bs = 0;
        for (; i + 2 < s; ++i) {
            // hash value
            var hv = hsh(i);
            // index mod 32768    previous index mod
            var imod = i & 32767, pimod = head[hv];
            prev[imod] = pimod;
            head[hv] = imod;
            // We always should modify head and prev, but only add symbols if
            // this data is not yet processed ("wait" for wait index)
            if (wi <= i) {
                // bytes remaining
                var rem = s - i;
                if ((lc_1 > 7000 || li > 24576) && (rem > 423 || !lst)) {
                    pos = wblk(dat, w, 0, syms, lf, df, eb, li, bs, i - bs, pos);
                    li = lc_1 = eb = 0, bs = i;
                    for (var j = 0; j < 286; ++j)
                        lf[j] = 0;
                    for (var j = 0; j < 30; ++j)
                        df[j] = 0;
                }
                //  len    dist   chain
                var l = 2, d = 0, ch_1 = c, dif = imod - pimod & 32767;
                if (rem > 2 && hv == hsh(i - dif)) {
                    var maxn = Math.min(n, rem) - 1;
                    var maxd = Math.min(32767, i);
                    // max possible length
                    // not capped at dif because decompressors implement "rolling" index population
                    var ml = Math.min(258, rem);
                    while (dif <= maxd && --ch_1 && imod != pimod) {
                        if (dat[i + l] == dat[i + l - dif]) {
                            var nl = 0;
                            for (; nl < ml && dat[i + nl] == dat[i + nl - dif]; ++nl)
                                ;
                            if (nl > l) {
                                l = nl, d = dif;
                                // break out early when we reach "nice" (we are satisfied enough)
                                if (nl > maxn)
                                    break;
                                // now, find the rarest 2-byte sequence within this
                                // length of literals and search for that instead.
                                // Much faster than just using the start
                                var mmd = Math.min(dif, nl - 2);
                                var md = 0;
                                for (var j = 0; j < mmd; ++j) {
                                    var ti = i - dif + j & 32767;
                                    var pti = prev[ti];
                                    var cd = ti - pti & 32767;
                                    if (cd > md)
                                        md = cd, pimod = ti;
                                }
                            }
                        }
                        // check the previous match
                        imod = pimod, pimod = prev[imod];
                        dif += imod - pimod & 32767;
                    }
                }
                // d will be nonzero only when a match was found
                if (d) {
                    // store both dist and len data in one int32
                    // Make sure this is recognized as a len/dist with 28th bit (2^28)
                    syms[li++] = 268435456 | (revfl[l] << 18) | revfd[d];
                    var lin = revfl[l] & 31, din = revfd[d] & 31;
                    eb += fleb[lin] + fdeb[din];
                    ++lf[257 + lin];
                    ++df[din];
                    wi = i + l;
                    ++lc_1;
                }
                else {
                    syms[li++] = dat[i];
                    ++lf[dat[i]];
                }
            }
        }
        for (i = Math.max(i, wi); i < s; ++i) {
            syms[li++] = dat[i];
            ++lf[dat[i]];
        }
        pos = wblk(dat, w, lst, syms, lf, df, eb, li, bs, i - bs, pos);
        if (!lst) {
            st.r = (pos & 7) | w[(pos / 8) | 0] << 3;
            // shft(pos) now 1 less if pos & 7 != 0
            pos -= 7;
            st.h = head, st.p = prev, st.i = i, st.w = wi;
        }
    }
    else {
        for (var i = st.w || 0; i < s + lst; i += 65535) {
            // end
            var e = i + 65535;
            if (e >= s) {
                // write final block
                w[(pos / 8) | 0] = lst;
                e = s;
            }
            pos = wfblk(w, pos + 1, dat.subarray(i, e));
        }
        st.i = s;
    }
    return slc(o, 0, pre + shft(pos) + post);
};
// CRC32 table
var crct = /*#__PURE__*/ (function () {
    var t = new Int32Array(256);
    for (var i = 0; i < 256; ++i) {
        var c = i, k = 9;
        while (--k)
            c = ((c & 1) && -306674912) ^ (c >>> 1);
        t[i] = c;
    }
    return t;
})();
// CRC32
var crc = function () {
    var c = -1;
    return {
        p: function (d) {
            // closures have awful performance
            var cr = c;
            for (var i = 0; i < d.length; ++i)
                cr = crct[(cr & 255) ^ d[i]] ^ (cr >>> 8);
            c = cr;
        },
        d: function () { return ~c; }
    };
};
// deflate with opts
var dopt = function (dat, opt, pre, post, st) {
    if (!st) {
        st = { l: 1 };
        if (opt.dictionary) {
            var dict = opt.dictionary.subarray(-32768);
            var newDat = new u8(dict.length + dat.length);
            newDat.set(dict);
            newDat.set(dat, dict.length);
            dat = newDat;
            st.w = dict.length;
        }
    }
    return dflt(dat, opt.level == null ? 6 : opt.level, opt.mem == null ? (st.l ? Math.ceil(Math.max(8, Math.min(13, Math.log(dat.length))) * 1.5) : 20) : (12 + opt.mem), pre, post, st);
};
// Walmart object spread
var mrg = function (a, b) {
    var o = {};
    for (var k in a)
        o[k] = a[k];
    for (var k in b)
        o[k] = b[k];
    return o;
};
// read 2 bytes
var b2 = function (d, b) { return d[b] | (d[b + 1] << 8); };
// read 4 bytes
var b4 = function (d, b) { return (d[b] | (d[b + 1] << 8) | (d[b + 2] << 16) | (d[b + 3] << 24)) >>> 0; };
// read 8 bytes
var b8 = function (d, b) { return b4(d, b) + (b4(d, b + 4) * 4294967296); };
// write bytes
var wbytes = function (d, b, v) {
    for (; v; ++b)
        d[b] = v, v >>>= 8;
};
/**
 * Compresses data with DEFLATE without any wrapper
 * @param data The data to compress
 * @param opts The compression options
 * @returns The deflated version of the data
 */
function deflateSync(data, opts) {
    return dopt(data, opts || {}, 0, 0);
}
function inflateSync(data, opts) {
    return inflt(data, { i: 2 }, opts && opts.out, opts && opts.dictionary);
}
// flatten a directory structure
var fltn = function (d, p, t, o) {
    for (var k in d) {
        var val = d[k], n = p + k, op = o;
        if (Array.isArray(val))
            op = mrg(o, val[1]), val = val[0];
        if (ArrayBuffer.isView(val))
            t[n] = [val, op];
        else {
            t[n += '/'] = [new u8(0), op];
            fltn(val, n, t, o);
        }
    }
};
// text encoder
var te = typeof TextEncoder != 'undefined' && /*#__PURE__*/ new TextEncoder();
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
 * Converts a string into a Uint8Array for use with compression/decompression methods
 * @param str The string to encode
 * @param latin1 Whether or not to interpret the data as Latin-1. This should
 *               not need to be true unless decoding a binary string.
 * @returns The string encoded in UTF-8/Latin-1 binary
 */
function strToU8(str, latin1) {
    var i;
    if (te)
        return te.encode(str);
    var l = str.length;
    var ar = new u8(str.length + (str.length >> 1));
    var ai = 0;
    var w = function (v) { ar[ai++] = v; };
    for (var i = 0; i < l; ++i) {
        if (ai + 5 > ar.length) {
            var n = new u8(ai + 8 + ((l - i) << 1));
            n.set(ar);
            ar = n;
        }
        var c = str.charCodeAt(i);
        if (c < 128 || latin1)
            w(c);
        else if (c < 2048)
            w(192 | (c >> 6)), w(128 | (c & 63));
        else if (c > 55295 && c < 57344)
            c = 65536 + (c & 1023 << 10) | (str.charCodeAt(++i) & 1023),
                w(240 | (c >> 18)), w(128 | ((c >> 12) & 63)), w(128 | ((c >> 6) & 63)), w(128 | (c & 63));
        else
            w(224 | (c >> 12)), w(128 | ((c >> 6) & 63)), w(128 | (c & 63));
    }
    return slc(ar, 0, ai);
}
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
// extra field length
var exfl = function (ex) {
    var le = 0;
    if (ex) {
        for (var k in ex) {
            var l = ex[k].length;
            if (l > 65535)
                err(9);
            le += l + 4;
        }
    }
    return le;
};
// write zip header
var wzh = function (d, b, f, fn, u, c, ce, co) {
    var fl = fn.length, ex = f.extra, col = co && co.length;
    var exl = exfl(ex);
    wbytes(d, b, ce != null ? 0x2014B50 : 0x4034B50), b += 4;
    if (ce != null)
        d[b++] = 20, d[b++] = f.os;
    d[b] = 20, b += 2; // spec compliance? what's that?
    d[b++] = (f.flag << 1) | (c < 0 && 8), d[b++] = u && 8;
    d[b++] = f.compression & 255, d[b++] = f.compression >> 8;
    var dt = new Date(f.mtime == null ? Date.now() : f.mtime), y = dt.getFullYear() - 1980;
    if (y < 0 || y > 119)
        err(10);
    wbytes(d, b, (y << 25) | ((dt.getMonth() + 1) << 21) | (dt.getDate() << 16) | (dt.getHours() << 11) | (dt.getMinutes() << 5) | (dt.getSeconds() >> 1)), b += 4;
    if (c != -1) {
        wbytes(d, b, f.crc);
        wbytes(d, b + 4, c < 0 ? -c - 2 : c);
        wbytes(d, b + 8, f.size);
    }
    wbytes(d, b + 12, fl);
    wbytes(d, b + 14, exl), b += 16;
    if (ce != null) {
        wbytes(d, b, col);
        wbytes(d, b + 6, f.attrs);
        wbytes(d, b + 10, ce), b += 14;
    }
    d.set(fn, b);
    b += fl;
    if (exl) {
        for (var k in ex) {
            var exf = ex[k], l = exf.length;
            wbytes(d, b, +k);
            wbytes(d, b + 2, l);
            d.set(exf, b + 4), b += 4 + l;
        }
    }
    if (col)
        d.set(co, b), b += col;
    return b;
};
// write zip footer (end of central directory)
var wzf = function (o, b, c, d, e) {
    wbytes(o, b, 0x6054B50); // skip disk
    wbytes(o, b + 8, c);
    wbytes(o, b + 10, c);
    wbytes(o, b + 12, d);
    wbytes(o, b + 16, e);
};
/**
 * Synchronously creates a ZIP file. Prefer using `zip` for better performance
 * with more than one file.
 * @param data The directory structure for the ZIP archive
 * @param opts The main options, merged with per-file options
 * @returns The generated ZIP archive
 */
function zipSync(data, opts) {
    if (!opts)
        opts = {};
    var r = {};
    var files = [];
    fltn(data, '', r, opts);
    var o = 0;
    var tot = 0;
    for (var fn in r) {
        var _a = r[fn], file = _a[0], p = _a[1];
        var compression = p.level == 0 ? 0 : 8;
        var f = strToU8(fn), s = f.length;
        var com = p.comment, m = com && strToU8(com), ms = m && m.length;
        var exl = exfl(p.extra);
        if (s > 65535)
            err(11);
        var d = compression ? deflateSync(file, p) : file, l = d.length;
        var c = crc();
        c.p(file);
        files.push(mrg(p, {
            size: file.length,
            crc: c.d(),
            c: d,
            f: f,
            m: m,
            u: s != fn.length || (m && (com.length != ms)),
            o: o,
            compression: compression
        }));
        o += 30 + s + exl + l;
        tot += 76 + 2 * (s + exl) + (ms || 0) + l;
    }
    var out = new u8(tot + 22), oe = o, cdl = tot - o;
    for (var i = 0; i < files.length; ++i) {
        var f = files[i];
        wzh(out, f.o, f, f.f, f.u, f.c.length);
        var badd = 30 + f.f.length + exfl(f.extra);
        out.set(f.c, f.o + badd);
        wzh(out, o, f, f.f, f.u, f.c.length, f.o, f.m), o += 16 + badd + (f.m ? f.m.length : 0);
    }
    wzf(out, o, files.length, cdl, oe);
    return out;
}
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

const MAX_ARCHIVE = 8 * 1024 * 1024;
const MAX_IMAGE = 4 * 1024 * 1024;
const MAX_MANIFEST = 64 * 1024;
const MAX_THUMB = 128 * 1024;
function imageMime(bytes) {
  if (bytes[0] === 137 && strFromU8(bytes.subarray(1, 4)) === "PNG") return "image/png";
  if (strFromU8(bytes.subarray(0, 4)) === "RIFF" && strFromU8(bytes.subarray(8, 12)) === "WEBP") return "image/webp";
  if (strFromU8(bytes.subarray(0, 3)) === "GIF") return "image/gif";
  if (bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255) return "image/jpeg";
  throw new Error("包内图片格式无效");
}
function imageDataUrl(bytes) {
  let binary = "";
  for (let start = 0; start < bytes.length; start += 8192)
    binary += String.fromCharCode(...bytes.subarray(start, start + 8192));
  return `data:${imageMime(bytes)};base64,${btoa(binary)}`;
}
async function imageBytes(src, limit) {
  if (src.startsWith("data:")) {
    const match = /^data:image\/[a-z0-9.+-]+;base64,([a-zA-Z0-9+/=]+)$/.exec(src);
    if (!match || match[1].length > Math.ceil(limit / 3) * 4) throw new Error("图片内容无效或超过大小限制");
    const bytes = Uint8Array.from(atob(match[1]), (char) => char.charCodeAt(0));
    if (bytes.length > limit) throw new Error("图片超过大小限制");
    imageMime(bytes);
    return bytes;
  }
  if (!/^https?:\/\/\S+$/.test(src)) throw new Error("图片地址无效");
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 12e3);
  try {
    const response = await fetch(src, { signal: controller.signal, credentials: "omit" });
    if (!response.ok || !response.body) throw new Error("远程图片读取失败");
    const reader = response.body.getReader();
    const chunks = [];
    let length = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        length += value.length;
        if (length > limit) {
          await reader.cancel();
          throw new Error("图片超过大小限制");
        }
        chunks.push(value);
      }
    } finally {
      reader.releaseLock();
    }
    const bytes = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.length;
    }
    imageMime(bytes);
    return bytes;
  } finally {
    window.clearTimeout(timeout);
  }
}
async function verifyImage(bytes, pack) {
  const bitmap = await createImageBitmap(new Blob([new Uint8Array(bytes)], { type: imageMime(bytes) }));
  try {
    if (!bitmap.width || !bitmap.height || bitmap.width > 4096 || bitmap.height > 4096)
      throw new Error("图片尺寸无效或超过 4096 像素");
    if (pack && (bitmap.width % pack.grid.cols || bitmap.height % pack.grid.rows))
      throw new Error("精灵图尺寸不能被素材网格整除");
  } finally {
    bitmap.close();
  }
}
async function exportPackArchive(api, pluginId, key) {
  const data = unwrap(
    await api.get(`plugin/${pluginId}/pack?key=${encodeURIComponent(key)}`)
  );
  if (!data || data.builtin || data.pack?.id !== key) throw new Error("只能导出已导入的素材");
  const { pack, errors } = validatePack(data.pack);
  if (!pack) throw new Error(errors.join("；"));
  const sheet = await imageBytes(data.sheet_src, MAX_IMAGE);
  await verifyImage(sheet, pack);
  const files = { "sheet.img": sheet };
  const images = { sheet: "sheet.img" };
  for (const field of ["preview", "avatar"]) {
    if (!data.pack[field]) continue;
    const bytes = await imageBytes(data.pack[field], MAX_THUMB);
    await verifyImage(bytes);
    files[`${field}.img`] = bytes;
    images[field] = `${field}.img`;
  }
  const metadata = { ...pack, sheet: "" };
  delete metadata.preview;
  delete metadata.avatar;
  const manifest = strToU8(JSON.stringify({ format: "agentpets", version: 1, pack: metadata, images }));
  if (manifest.length > MAX_MANIFEST) throw new Error("素材描述超过 64KB，未生成备份");
  files["agentpets.json"] = manifest;
  const archive = zipSync(files);
  if (archive.length > MAX_ARCHIVE) throw new Error("素材包超过 8MB");
  return new Blob([new Uint8Array(archive)], { type: "application/zip" });
}
function fileBytes(file) {
  if (file.arrayBuffer) return file.arrayBuffer().then((value) => new Uint8Array(value));
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result));
    reader.onerror = () => reject(new Error("无法读取素材包"));
    reader.readAsArrayBuffer(file);
  });
}
async function readPackArchive(file) {
  if (file.size > MAX_ARCHIVE) throw new Error("素材包不能超过 8MB");
  const allowed = /* @__PURE__ */ new Set(["agentpets.json", "sheet.img", "preview.img", "avatar.img"]);
  const seen = /* @__PURE__ */ new Set();
  const files = unzipSync(await fileBytes(file), {
    filter: (entry) => {
      if (!allowed.has(entry.name) || seen.has(entry.name)) throw new Error("素材包包含未知或重复文件");
      seen.add(entry.name);
      const limit = entry.name === "agentpets.json" ? MAX_MANIFEST : entry.name === "sheet.img" ? MAX_IMAGE : MAX_THUMB;
      if (entry.originalSize > limit) throw new Error("包内文件超过大小限制");
      return true;
    }
  });
  if (!files["agentpets.json"] || !files["sheet.img"])
    throw new Error("不是完整的 AgentPets 素材包；Codex Pet ZIP 请切换到“Codex Pet”导入类型");
  const manifest = JSON.parse(strFromU8(files["agentpets.json"]));
  if (manifest?.format !== "agentpets" || manifest?.version !== 1 || manifest?.images?.sheet !== "sheet.img")
    throw new Error("素材包格式或版本不支持");
  const { pack, errors } = validatePack(manifest.pack);
  if (!pack) throw new Error(errors.join("；"));
  pack.sheet = "";
  pack.preview = "";
  pack.avatar = "";
  await verifyImage(files["sheet.img"], pack);
  for (const field of ["preview", "avatar"]) {
    const path = manifest.images[field];
    if (path === void 0) continue;
    if (path !== `${field}.img` || !files[path]) throw new Error("素材包缺少头像或预览图片");
    await verifyImage(files[path]);
    pack[field] = imageDataUrl(files[path]);
  }
  return { pack, image: imageDataUrl(files["sheet.img"]) };
}

const {defineComponent:_defineComponent$3} = await importShared('vue');

const {createElementVNode:_createElementVNode$3,resolveComponent:_resolveComponent$3,createVNode:_createVNode$3,toDisplayString:_toDisplayString$3,createTextVNode:_createTextVNode$3,withCtx:_withCtx$3,openBlock:_openBlock$3,createBlock:_createBlock$3,createCommentVNode:_createCommentVNode$3,normalizeStyle:_normalizeStyle,createElementBlock:_createElementBlock$3,unref:_unref$3,Fragment:_Fragment$3} = await importShared('vue');

const _hoisted_1$3 = { class: "ap-archive-import" };
const _hoisted_2$3 = { class: "d-flex align-center ga-3 mb-3" };
const _hoisted_3$3 = ["aria-label"];
const _hoisted_4$3 = { class: "text-caption" };
const _hoisted_5$3 = {
  key: 1,
  class: "ap-archive-import__review"
};
const _hoisted_6$3 = { class: "d-flex justify-end ga-2 mt-3" };
const {computed: computed$3,inject: inject$3,onBeforeUnmount: onBeforeUnmount$3,ref: ref$3,watch: watch$3} = await importShared('vue');
const _sfc_main$3 = /* @__PURE__ */ _defineComponent$3({
  __name: "PackArchiveImport",
  props: {
    api: {},
    pluginId: {},
    targets: {}
  },
  emits: ["changed", "busy"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const agent = inject$3(AGENT_HOST_KEY, null);
    const file = ref$3(null);
    const archive = ref$3(null);
    const target = ref$3(null);
    const name = ref$3("");
    const mode = ref$3("new");
    const error = ref$3("");
    const message = ref$3("");
    const busy = ref$3(false);
    watch$3(busy, (value) => emit("busy", value));
    let alive = true;
    let operation = 0;
    onBeforeUnmount$3(() => {
      alive = false;
      operation++;
    });
    watch$3(
      () => props.pluginId,
      () => {
        operation++;
        busy.value = false;
        archive.value = null;
        target.value = null;
        file.value = null;
        error.value = "";
        message.value = "";
      }
    );
    const previewStyle = computed$3(() => {
      if (!archive.value) return {};
      const { pack, image } = archive.value;
      const position = framePosition(pack, "idle");
      return {
        backgroundImage: `url(${JSON.stringify(image)})`,
        backgroundSize: `${pack.grid.cols * 100}% ${pack.grid.rows * 100}%`,
        backgroundPosition: `${position.x}% ${position.y}%`
      };
    });
    const duplicateName = computed$3(
      () => props.targets.some(
        (item) => item.name === name.value.trim() && (mode.value !== "replace" || item.id !== target.value?.id)
      )
    );
    const stale = computed$3(
      () => mode.value === "replace" && props.targets.find((item) => item.id === target.value?.id)?.revision !== target.value?.revision
    );
    const valid = computed$3(
      () => !!archive.value && !!name.value.trim() && [...name.value.trim()].length <= 40 && !busy.value && !stale.value && (mode.value !== "replace" || !!target.value?.revision && !target.value.builtin)
    );
    const choices = computed$3(
      () => target.value ? [
        { title: "导入副本（保留已有素材）", value: "copy" },
        ...!target.value.builtin ? [{ title: "更新同 ID 素材", value: "replace" }] : []
      ] : [{ title: "新增素材", value: "new" }]
    );
    watch$3(mode, (value) => {
      if (value === "replace" && archive.value) name.value = archive.value.pack.name;
    });
    async function read(value) {
      const nextFile = value === void 0 ? file.value : Array.isArray(value) ? value[0] : value;
      file.value = nextFile ?? null;
      const version = ++operation;
      const instance = props.pluginId;
      archive.value = null;
      error.value = "";
      message.value = "";
      if (!nextFile) {
        busy.value = false;
        return;
      }
      busy.value = true;
      try {
        const result = await readPackArchive(nextFile);
        if (!alive || version !== operation || instance !== props.pluginId) return;
        archive.value = result;
        const match = props.targets.find((item) => item.id === result.pack.id);
        target.value = match ? { ...match } : null;
        mode.value = target.value ? "copy" : "new";
        name.value = props.targets.some((item) => item.name === result.pack.name) ? result.pack.name.slice(0, 35) + "（副本）" : result.pack.name;
      } catch (reason) {
        if (alive && version === operation) error.value = reason instanceof Error ? reason.message : "素材包读取失败";
      } finally {
        if (alive && version === operation) busy.value = false;
      }
    }
    async function submit() {
      if (!valid.value || !props.api || !archive.value) return;
      const instance = props.pluginId;
      const version = ++operation;
      const key = archive.value.pack.id;
      const request = {
        pack: { ...archive.value.pack, name: name.value.trim() },
        image: archive.value.image,
        mode: mode.value,
        expected_revision: mode.value === "replace" ? target.value?.revision : void 0
      };
      busy.value = true;
      error.value = "";
      try {
        const response = await props.api.post(`plugin/${instance}/packs/import`, request);
        if (!alive || version !== operation || instance !== props.pluginId) return;
        if (!response?.success || !response.data?.id || request.mode === "replace" && response.data.id !== key)
          throw new Error(response?.message || "导入结果未确认，请刷新后核对");
        if (request.mode === "replace") agent?.emit(PACK_UPDATED_EVENT, { key });
        message.value = `已${request.mode === "replace" ? "更新" : "导入"} ${response.data.name}`;
        archive.value = null;
        emit("changed");
      } catch (reason) {
        if (alive && version === operation)
          error.value = reason instanceof Error ? reason.message : "导入失败，请刷新后核对";
      } finally {
        if (alive && version === operation) busy.value = false;
      }
    }
    return (_ctx, _cache) => {
      const _component_v_file_input = _resolveComponent$3("v-file-input");
      const _component_v_alert = _resolveComponent$3("v-alert");
      const _component_v_img = _resolveComponent$3("v-img");
      const _component_v_avatar = _resolveComponent$3("v-avatar");
      const _component_v_select = _resolveComponent$3("v-select");
      const _component_v_text_field = _resolveComponent$3("v-text-field");
      const _component_v_btn = _resolveComponent$3("v-btn");
      return _openBlock$3(), _createElementBlock$3("section", _hoisted_1$3, [
        _cache[13] || (_cache[13] = _createElementVNode$3("p", { class: "ap-muted mb-3" }, "选择从素材卡片导出的完整 ZIP，预览后可导入副本，或核对后更新同 ID 素材。", -1)),
        _createVNode$3(_component_v_file_input, {
          "model-value": file.value ? [file.value] : [],
          label: "选择 AgentPets 导出 ZIP",
          accept: ".zip",
          density: "compact",
          variant: "outlined",
          disabled: busy.value,
          loading: busy.value,
          "prepend-icon": "",
          "prepend-inner-icon": "mdi-package-up",
          "onUpdate:modelValue": read
        }, null, 8, ["model-value", "disabled", "loading"]),
        error.value ? (_openBlock$3(), _createBlock$3(_component_v_alert, {
          key: 0,
          type: "error",
          variant: "tonal",
          density: "compact"
        }, {
          default: _withCtx$3(() => [
            _createTextVNode$3(_toDisplayString$3(error.value), 1)
          ]),
          _: 1
        })) : _createCommentVNode$3("", true),
        message.value ? (_openBlock$3(), _createBlock$3(_component_v_alert, {
          key: 1,
          type: "success",
          variant: "tonal",
          density: "compact"
        }, {
          default: _withCtx$3(() => [
            _createTextVNode$3(_toDisplayString$3(message.value), 1)
          ]),
          _: 1
        })) : _createCommentVNode$3("", true),
        archive.value ? (_openBlock$3(), _createElementBlock$3(_Fragment$3, { key: 2 }, [
          _createElementVNode$3("div", _hoisted_2$3, [
            archive.value.pack.preview || archive.value.pack.avatar ? (_openBlock$3(), _createBlock$3(_component_v_avatar, {
              key: 0,
              size: "64",
              rounded: "lg"
            }, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_img, {
                  src: archive.value.pack.preview || archive.value.pack.avatar,
                  alt: archive.value.pack.name
                }, null, 8, ["src", "alt"])
              ]),
              _: 1
            })) : (_openBlock$3(), _createElementBlock$3("div", {
              key: 1,
              class: "ap-archive-import__preview",
              style: _normalizeStyle(previewStyle.value),
              role: "img",
              "aria-label": archive.value.pack.name
            }, null, 12, _hoisted_3$3)),
            _createElementVNode$3("div", null, [
              _createElementVNode$3("strong", null, _toDisplayString$3(archive.value.pack.name), 1),
              _createElementVNode$3("div", _hoisted_4$3, _toDisplayString$3(archive.value.pack.grid.cols) + " × " + _toDisplayString$3(archive.value.pack.grid.rows) + " 网格 · " + _toDisplayString$3(Object.keys(archive.value.pack.actions).length) + " 项动作 ", 1)
            ])
          ]),
          _createVNode$3(_component_v_select, {
            modelValue: mode.value,
            "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => mode.value = $event),
            items: choices.value,
            label: "导入方式",
            density: "compact",
            variant: "outlined",
            disabled: busy.value
          }, null, 8, ["modelValue", "items", "disabled"]),
          _createVNode$3(_component_v_text_field, {
            modelValue: name.value,
            "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => name.value = $event),
            label: "导入后的名称",
            counter: "40",
            density: "compact",
            variant: "outlined",
            disabled: busy.value
          }, null, 8, ["modelValue", "disabled"]),
          duplicateName.value ? (_openBlock$3(), _createBlock$3(_component_v_alert, {
            key: 0,
            type: "warning",
            variant: "tonal",
            density: "compact",
            class: "mb-3"
          }, {
            default: _withCtx$3(() => [..._cache[3] || (_cache[3] = [
              _createTextVNode$3("已有同名素材，可修改名称区分；名称相同不会自动覆盖。", -1)
            ])]),
            _: 1
          })) : _createCommentVNode$3("", true),
          mode.value === "replace" && target.value ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_5$3, [
            _createElementVNode$3("table", null, [
              _cache[9] || (_cache[9] = _createElementVNode$3("thead", null, [
                _createElementVNode$3("tr", null, [
                  _createElementVNode$3("th", null, "内容"),
                  _createElementVNode$3("th", null, "当前素材"),
                  _createElementVNode$3("th", null, "导入后")
                ])
              ], -1)),
              _createElementVNode$3("tbody", null, [
                _createElementVNode$3("tr", null, [
                  _cache[4] || (_cache[4] = _createElementVNode$3("td", null, "名称", -1)),
                  _createElementVNode$3("td", null, _toDisplayString$3(target.value.name), 1),
                  _createElementVNode$3("td", null, _toDisplayString$3(name.value), 1)
                ]),
                _createElementVNode$3("tr", null, [
                  _cache[5] || (_cache[5] = _createElementVNode$3("td", null, "网格", -1)),
                  _createElementVNode$3("td", null, _toDisplayString$3(target.value.grid?.cols) + " × " + _toDisplayString$3(target.value.grid?.rows), 1),
                  _createElementVNode$3("td", null, _toDisplayString$3(archive.value.pack.grid.cols) + " × " + _toDisplayString$3(archive.value.pack.grid.rows), 1)
                ]),
                _createElementVNode$3("tr", null, [
                  _cache[6] || (_cache[6] = _createElementVNode$3("td", null, "帧／动作数量", -1)),
                  _createElementVNode$3("td", null, _toDisplayString$3(target.value.frame_count) + "／" + _toDisplayString$3(target.value.action_count), 1),
                  _createElementVNode$3("td", null, _toDisplayString$3(Object.keys(archive.value.pack.frames).length) + "／" + _toDisplayString$3(Object.keys(archive.value.pack.actions).length), 1)
                ]),
                _createElementVNode$3("tr", null, [
                  _cache[7] || (_cache[7] = _createElementVNode$3("td", null, "自定义映射数量", -1)),
                  _createElementVNode$3("td", null, _toDisplayString$3(target.value.mapping_count ?? 0), 1),
                  _createElementVNode$3("td", null, _toDisplayString$3(Object.keys(archive.value.pack.action_mappings ?? {}).length), 1)
                ]),
                _createElementVNode$3("tr", null, [
                  _cache[8] || (_cache[8] = _createElementVNode$3("td", null, "显示校准", -1)),
                  _createElementVNode$3("td", null, _toDisplayString$3(target.value.calibrated ? "已调整" : "默认"), 1),
                  _createElementVNode$3("td", null, _toDisplayString$3(_unref$3(sameCalibration)(archive.value.pack.calibration) ? "默认" : "已调整"), 1)
                ])
              ])
            ]),
            _cache[10] || (_cache[10] = _createElementVNode$3("p", { class: "text-caption mt-2" }, " 将替换此 ID 的名称、说明、图片、头像、预览、帧与动作、映射及校准；原记录与已上传原图会保留恢复副本。当前形象选择和个人位置保留。 ", -1))
          ])) : _createCommentVNode$3("", true),
          stale.value ? (_openBlock$3(), _createBlock$3(_component_v_alert, {
            key: 2,
            type: "warning",
            variant: "tonal",
            density: "compact"
          }, {
            default: _withCtx$3(() => [..._cache[11] || (_cache[11] = [
              _createTextVNode$3("当前素材已变化，请重新读取并核对覆盖范围。", -1)
            ])]),
            _: 1
          })) : _createCommentVNode$3("", true),
          _createElementVNode$3("div", _hoisted_6$3, [
            _createVNode$3(_component_v_btn, {
              variant: "text",
              disabled: busy.value,
              onClick: _cache[2] || (_cache[2] = ($event) => read())
            }, {
              default: _withCtx$3(() => [..._cache[12] || (_cache[12] = [
                _createTextVNode$3("重新读取", -1)
              ])]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode$3(_component_v_btn, {
              color: "primary",
              variant: "flat",
              disabled: !valid.value,
              loading: busy.value,
              onClick: submit
            }, {
              default: _withCtx$3(() => [
                _createTextVNode$3(_toDisplayString$3(mode.value === "replace" ? "确认覆盖此素材" : "确认导入"), 1)
              ]),
              _: 1
            }, 8, ["disabled", "loading"])
          ])
        ], 64)) : _createCommentVNode$3("", true)
      ]);
    };
  }
});

const PackArchiveImport = /* @__PURE__ */ _export_sfc(_sfc_main$3, [["__scopeId", "data-v-a20b81a4"]]);

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

const {createElementVNode:_createElementVNode$2,resolveComponent:_resolveComponent$2,createVNode:_createVNode$2,toDisplayString:_toDisplayString$2,createTextVNode:_createTextVNode$2,withCtx:_withCtx$2,openBlock:_openBlock$2,createBlock:_createBlock$2,createCommentVNode:_createCommentVNode$2,renderList:_renderList$2,Fragment:_Fragment$2,createElementBlock:_createElementBlock$2,withModifiers:_withModifiers$1,withKeys:_withKeys,vShow:_vShow$1,withDirectives:_withDirectives$1,unref:_unref$2} = await importShared('vue');

const _hoisted_1$2 = { class: "agent-pet-sprites-config" };
const _hoisted_2$2 = { class: "ap-inline mb-2" };
const _hoisted_3$2 = {
  class: "agent-pet-sprites-config__list mb-6",
  role: "list",
  "aria-label": "已有 Pet 素材"
};
const _hoisted_4$2 = { class: "agent-pet-sprites-config__info" };
const _hoisted_5$2 = ["title"];
const _hoisted_6$2 = { class: "agent-pet-sprites-config__meta" };
const _hoisted_7$2 = { class: "agent-pet-sprites-config__actions" };
const _hoisted_8$2 = {
  key: 0,
  class: "agent-pet-sprites-config__empty ap-muted"
};
const _hoisted_9$2 = { class: "agent-pet-sprites-config__import" };
const _hoisted_10$2 = { class: "ap-section-heading" };
const _hoisted_11$2 = { class: "d-flex align-center justify-end flex-wrap ga-2 mt-4" };
const {computed: computed$2,inject: inject$2,onBeforeUnmount: onBeforeUnmount$2,onMounted,ref: ref$2,watch: watch$2} = await importShared('vue');
const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
const _sfc_main$2 = /* @__PURE__ */ _defineComponent$2({
  __name: "PackManager",
  props: {
    api: { default: null },
    pluginId: { default: "" }
  },
  emits: ["changed"],
  setup(__props, { expose: __expose, emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const importMode = ref$2("codex");
    const archiveBusy = ref$2(false);
    let previousInputMode = "codex";
    const listError = ref$2("");
    const deleting = ref$2("");
    const exporting = ref$2("");
    const renameTarget = ref$2(null);
    const renameName = ref$2("");
    const renameError = ref$2("");
    const renaming = ref$2(false);
    const agent = inject$2(AGENT_HOST_KEY, null);
    const renameValid = computed$2(() => !!renameName.value.trim() && [...renameName.value.trim()].length <= 40);
    let alive = true;
    let listVersion = 0;
    let instanceVersion = 0;
    onBeforeUnmount$2(() => {
      alive = false;
      instanceVersion++;
      listVersion++;
    });
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
    const toast = inject$2("moviepilot:toast", null);
    const confirm = inject$2("moviepilot:confirm", null);
    const instanceId = computed$2(() => props.pluginId || "AgentPets");
    const packs = ref$2([]);
    const loading = ref$2(false);
    const submitting = ref$2(false);
    const codexImporting = ref$2(false);
    const packText = ref$2("");
    const imageMode = ref$2("upload");
    watch$2(importMode, (value) => {
      if (value === "archive") return;
      if (value === "codex" && previousInputMode !== "codex") {
        imageMode.value = "upload";
        parsedCodexFile.value = null;
        packText.value = "";
        importMessage.value = "";
      }
      previousInputMode = value;
    });
    const selectedFile = ref$2(null);
    const parsedCodexFile = ref$2(null);
    const imageFile = ref$2(null);
    const fileModel = ref$2([]);
    const imageError = ref$2("");
    const importMessage = ref$2("");
    const importError = ref$2("");
    const serverError = ref$2("");
    const validation = computed$2(() => packText.value.trim() ? validatePack(packText.value) : null);
    const clientErrors = computed$2(() => {
      const errors = [...validation.value?.errors ?? []];
      if (imageMode.value === "url" && validation.value?.pack && !/^https?:\/\/\S+$/.test(validation.value.pack.sheet)) {
        errors.push("填写 URL 方式时，JSON 的 sheet 必须是 http(s) 图片地址");
      }
      return errors;
    });
    const canSubmit = computed$2(
      () => importMode.value !== "archive" && !!validation.value?.pack && !clientErrors.value.length && !submitting.value && (importMode.value !== "codex" || !!selectedFile.value && parsedCodexFile.value === selectedFile.value) && (imageMode.value === "url" || !!imageFile.value && !imageError.value)
    );
    function captureScope() {
      const version = instanceVersion;
      return { api: props.api, id: instanceId.value, current: () => alive && version === instanceVersion };
    }
    function previewSrc(pack) {
      if (pack.builtin) return builtinAvatar(pack.id);
      return pack.preview;
    }
    function notify(kind, message) {
      toast?.[kind]?.(message);
    }
    async function refresh() {
      if (!props.api?.get) {
        listError.value = "页面连接尚未就绪";
        return;
      }
      const version = ++listVersion;
      loading.value = true;
      listError.value = "";
      try {
        const response = await props.api.get(`plugin/${instanceId.value}/packs`);
        if (!alive || version !== listVersion) return;
        if (!response?.success || !Array.isArray(response.data)) throw new Error("invalid packs");
        packs.value = response.data;
      } catch {
        if (alive && version === listVersion) listError.value = "素材列表读取失败，请刷新重试";
      } finally {
        if (alive && version === listVersion) loading.value = false;
      }
    }
    function onImage(value) {
      const file = Array.isArray(value) ? value[0] ?? null : value ?? null;
      selectedFile.value = file;
      parsedCodexFile.value = null;
      if (importMode.value === "codex") packText.value = "";
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
      if (!file || imageError.value || codexImporting.value) return;
      const { current } = captureScope();
      codexImporting.value = true;
      parsedCodexFile.value = null;
      if (importMode.value === "codex") packText.value = "";
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
        if (!current()) return;
        const bitmap = await createImageBitmap(image);
        const { width, height } = bitmap;
        bitmap.close();
        if (!current()) return;
        const result = buildCodexPetPack(image.name, width, height, metadata);
        imageMode.value = "upload";
        imageFile.value = image;
        packText.value = JSON.stringify(result.pack, null, 2);
        parsedCodexFile.value = file;
        serverError.value = "";
        importMessage.value = (metadata ? "已从 Codex Pet 包读取精灵图，" : "已识别 Codex Pet ") + result.version + "，动作映射已生成";
      } catch (error) {
        if (!current()) return;
        importError.value = error instanceof Error ? error.message : "无法读取 Codex Pet 精灵图";
      } finally {
        if (current()) codexImporting.value = false;
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
      const { api, id, current } = captureScope();
      const pack = packText.value;
      const file = imageMode.value === "upload" ? imageFile.value : null;
      submitting.value = true;
      serverError.value = "";
      try {
        const image = file ? await readDataUrl(file) : null;
        if (!current()) return;
        const response = await api.post(`plugin/${id}/packs`, {
          pack,
          image
        });
        if (!current()) return;
        if (!response?.success) {
          serverError.value = response?.message || "添加失败";
          return;
        }
        notify("success", `已添加 Pet ${response.data?.name ?? ""}`);
        emit("changed");
        packText.value = "";
        selectedFile.value = null;
        parsedCodexFile.value = null;
        imageFile.value = null;
        fileModel.value = [];
        importMessage.value = "";
        importError.value = "";
        await refresh();
      } catch {
        if (current()) serverError.value = "添加失败，请检查网络或稍后重试";
      } finally {
        if (current()) submitting.value = false;
      }
    }
    async function removePack(pack) {
      if (!props.api?.post) return;
      const { api, id, current } = captureScope();
      const accepted = confirm ? await confirm({
        type: "warn",
        title: "删除素材包",
        content: `删除「${pack.name}」后，选择它的用户会回到内置机器人。`
      }) : window.confirm(`删除素材包「${pack.name}」？`);
      if (!accepted || !current()) return;
      deleting.value = pack.id;
      listError.value = "";
      try {
        const response = await api.post(`plugin/${id}/packs/delete`, { id: pack.id });
        if (!current()) return;
        if (response?.success) {
          notify("success", `已删除素材包 ${pack.name}`);
          emit("changed");
          await refresh();
        } else listError.value = response?.message || "删除失败";
      } catch {
        if (current()) listError.value = "删除未完成，请刷新核对后重试";
      } finally {
        if (current()) deleting.value = "";
      }
    }
    async function exportPack(pack) {
      if (!props.api || exporting.value) return;
      const { api, id, current } = captureScope();
      exporting.value = pack.id;
      listError.value = "";
      try {
        const blob = await exportPackArchive(api, id, pack.id);
        if (!current()) return;
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `${pack.id}.agentpets.zip`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1e3);
      } catch (reason) {
        if (current()) listError.value = `未生成完整素材包：${reason instanceof Error ? reason.message : "图片读取失败"}`;
      } finally {
        if (current()) exporting.value = "";
      }
    }
    function archiveImported() {
      emit("changed");
      void refresh();
    }
    function startRename(pack) {
      renameTarget.value = pack;
      renameName.value = pack.name;
      renameError.value = "";
    }
    async function renamePack() {
      if (renaming.value || !renameValid.value || !props.api || !renameTarget.value) return;
      const target = renameTarget.value;
      const { api, id, current } = captureScope();
      const name = renameName.value.trim();
      renaming.value = true;
      renameError.value = "";
      try {
        const response = await api.post(`plugin/${id}/packs/rename`, {
          id: target.id,
          name,
          expected_name: target.name
        });
        if (!current()) return;
        if (!response?.success || response.data?.id !== target.id || response.data?.name !== name) {
          renameError.value = response?.message || "重命名未确认，请刷新后核对";
          return;
        }
        packs.value = packs.value.map((pack) => pack.id === target.id ? response.data : pack);
        renameTarget.value = null;
        agent?.emit?.(PACK_UPDATED_EVENT, { key: target.id });
        emit("changed");
      } catch {
        if (current()) renameError.value = "重命名未完成，请刷新核对后重试";
      } finally {
        if (current()) renaming.value = false;
      }
    }
    watch$2(instanceId, () => {
      instanceVersion++;
      listVersion++;
      packs.value = [];
      submitting.value = false;
      codexImporting.value = false;
      archiveBusy.value = false;
      deleting.value = "";
      packText.value = "";
      selectedFile.value = null;
      parsedCodexFile.value = null;
      imageFile.value = null;
      fileModel.value = [];
      imageError.value = "";
      importMessage.value = "";
      importError.value = "";
      serverError.value = "";
      previousInputMode = "codex";
      importMode.value = "codex";
      imageMode.value = "upload";
      exporting.value = "";
      renameTarget.value = null;
      renaming.value = false;
      void refresh();
    });
    onMounted(refresh);
    __expose({ refresh });
    return (_ctx, _cache) => {
      const _component_v_spacer = _resolveComponent$2("v-spacer");
      const _component_v_btn = _resolveComponent$2("v-btn");
      const _component_v_alert = _resolveComponent$2("v-alert");
      const _component_v_progress_linear = _resolveComponent$2("v-progress-linear");
      const _component_v_img = _resolveComponent$2("v-img");
      const _component_v_icon = _resolveComponent$2("v-icon");
      const _component_v_avatar = _resolveComponent$2("v-avatar");
      const _component_v_chip = _resolveComponent$2("v-chip");
      const _component_v_text_field = _resolveComponent$2("v-text-field");
      const _component_v_card_text = _resolveComponent$2("v-card-text");
      const _component_v_card_actions = _resolveComponent$2("v-card-actions");
      const _component_v_card = _resolveComponent$2("v-card");
      const _component_v_dialog = _resolveComponent$2("v-dialog");
      const _component_v_btn_toggle = _resolveComponent$2("v-btn-toggle");
      const _component_v_textarea = _resolveComponent$2("v-textarea");
      const _component_v_file_input = _resolveComponent$2("v-file-input");
      const _component_v_expansion_panel_text = _resolveComponent$2("v-expansion-panel-text");
      const _component_v_expansion_panel = _resolveComponent$2("v-expansion-panel");
      const _component_v_expansion_panels = _resolveComponent$2("v-expansion-panels");
      return _openBlock$2(), _createElementBlock$2("div", _hoisted_1$2, [
        _createElementVNode$2("div", _hoisted_2$2, [
          _cache[9] || (_cache[9] = _createElementVNode$2("h3", { class: "ap-section-title mb-0" }, "我的素材", -1)),
          _createVNode$2(_component_v_spacer),
          _createVNode$2(_component_v_btn, {
            icon: "mdi-refresh",
            "aria-label": "刷新素材列表",
            variant: "text",
            size: "small",
            loading: loading.value,
            onClick: refresh
          }, null, 8, ["loading"])
        ]),
        listError.value ? (_openBlock$2(), _createBlock$2(_component_v_alert, {
          key: 0,
          type: "error",
          variant: "tonal",
          density: "compact",
          class: "mb-3"
        }, {
          default: _withCtx$2(() => [
            _createTextVNode$2(_toDisplayString$2(listError.value), 1)
          ]),
          _: 1
        })) : _createCommentVNode$2("", true),
        loading.value ? (_openBlock$2(), _createBlock$2(_component_v_progress_linear, {
          key: 1,
          indeterminate: "",
          color: "primary"
        })) : _createCommentVNode$2("", true),
        _createElementVNode$2("div", _hoisted_3$2, [
          (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(packs.value, (pack) => {
            return _openBlock$2(), _createElementBlock$2("article", {
              key: pack.id,
              class: "agent-pet-sprites-config__card",
              role: "listitem"
            }, [
              _createVNode$2(_component_v_avatar, {
                rounded: "lg",
                size: "52",
                class: "agent-pet-sprites-config__thumb"
              }, {
                default: _withCtx$2(() => [
                  previewSrc(pack) ? (_openBlock$2(), _createBlock$2(_component_v_img, {
                    key: 0,
                    src: previewSrc(pack),
                    alt: pack.name
                  }, null, 8, ["src", "alt"])) : (_openBlock$2(), _createBlock$2(_component_v_icon, {
                    key: 1,
                    icon: "mdi-image-outline"
                  }))
                ]),
                _: 2
              }, 1024),
              _createElementVNode$2("div", _hoisted_4$2, [
                _createElementVNode$2("div", {
                  class: "agent-pet-sprites-config__name",
                  title: pack.name
                }, _toDisplayString$2(pack.name), 9, _hoisted_5$2),
                _createElementVNode$2("div", _hoisted_6$2, [
                  _createElementVNode$2("span", null, _toDisplayString$2(pack.builtin ? "内置素材" : "已导入"), 1),
                  _createElementVNode$2("span", null, _toDisplayString$2(pack.mode === "stage" ? "自由活动" : "入口形象"), 1),
                  _createElementVNode$2("span", null, _toDisplayString$2(pack.action_count) + " 项动作定义", 1)
                ])
              ]),
              _createElementVNode$2("div", _hoisted_7$2, [
                pack.builtin ? (_openBlock$2(), _createBlock$2(_component_v_chip, {
                  key: 0,
                  size: "x-small",
                  variant: "tonal"
                }, {
                  default: _withCtx$2(() => [..._cache[10] || (_cache[10] = [
                    _createTextVNode$2("内置", -1)
                  ])]),
                  _: 1
                })) : _createCommentVNode$2("", true),
                !pack.builtin ? (_openBlock$2(), _createBlock$2(_component_v_btn, {
                  key: 1,
                  icon: "mdi-download-outline",
                  variant: "text",
                  size: "small",
                  "aria-label": `导出 ${pack.name}`,
                  loading: exporting.value === pack.id,
                  disabled: !!exporting.value || !!deleting.value || submitting.value || renaming.value,
                  onClick: ($event) => exportPack(pack)
                }, null, 8, ["aria-label", "loading", "disabled", "onClick"])) : _createCommentVNode$2("", true),
                !pack.builtin && pack.mode === "stage" ? (_openBlock$2(), _createBlock$2(_component_v_btn, {
                  key: 2,
                  icon: "mdi-pencil-outline",
                  variant: "text",
                  size: "small",
                  "aria-label": `重命名 ${pack.name}`,
                  disabled: !!deleting.value || submitting.value || renaming.value,
                  onClick: ($event) => startRename(pack)
                }, null, 8, ["aria-label", "disabled", "onClick"])) : _createCommentVNode$2("", true),
                !pack.builtin ? (_openBlock$2(), _createBlock$2(_component_v_btn, {
                  key: 3,
                  icon: "mdi-delete-outline",
                  variant: "text",
                  size: "small",
                  "aria-label": `删除 ${pack.name}`,
                  loading: deleting.value === pack.id,
                  disabled: !!deleting.value || submitting.value || renaming.value,
                  onClick: ($event) => removePack(pack)
                }, null, 8, ["aria-label", "loading", "disabled", "onClick"])) : _createCommentVNode$2("", true)
              ])
            ]);
          }), 128)),
          !packs.value.length && !loading.value && !listError.value ? (_openBlock$2(), _createElementBlock$2("p", _hoisted_8$2, " 暂无素材，导入一个 Pet 开始吧 ")) : _createCommentVNode$2("", true)
        ]),
        _createVNode$2(_component_v_dialog, {
          "model-value": !!renameTarget.value,
          "max-width": "420",
          persistent: renaming.value,
          "onUpdate:modelValue": _cache[2] || (_cache[2] = ($event) => !$event && !renaming.value && (renameTarget.value = null))
        }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_card, { title: "重命名 Pet" }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_card_text, null, {
                  default: _withCtx$2(() => [
                    _createVNode$2(_component_v_text_field, {
                      modelValue: renameName.value,
                      "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => renameName.value = $event),
                      label: "显示名称",
                      density: "compact",
                      variant: "outlined",
                      counter: "40",
                      disabled: renaming.value,
                      "error-messages": renameError.value || (!renameValid.value ? "请输入 1～40 个字符的名称" : ""),
                      onKeydown: _withKeys(_withModifiers$1(renamePack, ["prevent"]), ["enter"])
                    }, null, 8, ["modelValue", "disabled", "error-messages", "onKeydown"]),
                    _cache[11] || (_cache[11] = _createElementVNode$2("p", { class: "ap-muted mb-0" }, "只修改名称，当前选择、动作映射和位置保持不变。", -1))
                  ]),
                  _: 1
                }),
                _createVNode$2(_component_v_card_actions, null, {
                  default: _withCtx$2(() => [
                    _createVNode$2(_component_v_spacer),
                    _createVNode$2(_component_v_btn, {
                      variant: "text",
                      disabled: renaming.value,
                      onClick: _cache[1] || (_cache[1] = ($event) => renameTarget.value = null)
                    }, {
                      default: _withCtx$2(() => [..._cache[12] || (_cache[12] = [
                        _createTextVNode$2("取消", -1)
                      ])]),
                      _: 1
                    }, 8, ["disabled"]),
                    _createVNode$2(_component_v_btn, {
                      variant: "flat",
                      color: "primary",
                      disabled: !renameValid.value || renameName.value.trim() === renameTarget.value?.name,
                      loading: renaming.value,
                      onClick: renamePack
                    }, {
                      default: _withCtx$2(() => [..._cache[13] || (_cache[13] = [
                        _createTextVNode$2("保存名称", -1)
                      ])]),
                      _: 1
                    }, 8, ["disabled", "loading"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }, 8, ["model-value", "persistent"]),
        _createElementVNode$2("div", _hoisted_9$2, [
          _createElementVNode$2("div", _hoisted_10$2, [
            _createVNode$2(_component_v_icon, {
              icon: "mdi-package-down",
              color: "primary"
            }),
            _cache[14] || (_cache[14] = _createElementVNode$2("div", null, [
              _createElementVNode$2("h2", null, "导入 Pet"),
              _createElementVNode$2("p", null, "支持 Codex Pet、AgentPets 导出包和自定义精灵图，读取并核对后再导入。")
            ], -1))
          ]),
          _createVNode$2(_component_v_btn_toggle, {
            modelValue: importMode.value,
            "onUpdate:modelValue": _cache[3] || (_cache[3] = ($event) => importMode.value = $event),
            mandatory: "",
            density: "compact",
            color: "primary",
            variant: "tonal",
            class: "agent-pet-sprites-config__import-modes mb-4",
            "aria-label": "导入类型",
            disabled: submitting.value || codexImporting.value || archiveBusy.value
          }, {
            default: _withCtx$2(() => [
              _createVNode$2(_component_v_btn, { value: "codex" }, {
                default: _withCtx$2(() => [..._cache[15] || (_cache[15] = [
                  _createTextVNode$2("Codex Pet", -1)
                ])]),
                _: 1
              }),
              _createVNode$2(_component_v_btn, { value: "archive" }, {
                default: _withCtx$2(() => [..._cache[16] || (_cache[16] = [
                  _createTextVNode$2("AgentPets 素材包", -1)
                ])]),
                _: 1
              }),
              _createVNode$2(_component_v_btn, { value: "custom" }, {
                default: _withCtx$2(() => [..._cache[17] || (_cache[17] = [
                  _createTextVNode$2("自定义素材", -1)
                ])]),
                _: 1
              })
            ]),
            _: 1
          }, 8, ["modelValue", "disabled"]),
          _withDirectives$1(_createVNode$2(PackArchiveImport, {
            api: __props.api,
            "plugin-id": instanceId.value,
            targets: packs.value,
            onBusy: _cache[4] || (_cache[4] = ($event) => archiveBusy.value = $event),
            onChanged: archiveImported
          }, null, 8, ["api", "plugin-id", "targets"]), [
            [_vShow$1, importMode.value === "archive"]
          ]),
          _withDirectives$1(_createElementVNode$2("div", null, [
            importMode.value === "custom" ? (_openBlock$2(), _createElementBlock$2(_Fragment$2, { key: 0 }, [
              _createVNode$2(_component_v_textarea, {
                modelValue: packText.value,
                "onUpdate:modelValue": _cache[5] || (_cache[5] = ($event) => packText.value = $event),
                label: "素材包 JSON",
                placeholder: _unref$2(EXAMPLE),
                rows: "6",
                variant: "outlined",
                density: "compact",
                class: "agent-pet-sprites-config__json",
                "hide-details": "auto",
                disabled: submitting.value
              }, null, 8, ["modelValue", "placeholder", "disabled"]),
              _createVNode$2(_component_v_btn_toggle, {
                modelValue: imageMode.value,
                "onUpdate:modelValue": _cache[6] || (_cache[6] = ($event) => imageMode.value = $event),
                mandatory: "",
                density: "compact",
                variant: "outlined",
                class: "my-3",
                disabled: submitting.value || codexImporting.value
              }, {
                default: _withCtx$2(() => [
                  _createVNode$2(_component_v_btn, { value: "upload" }, {
                    default: _withCtx$2(() => [..._cache[18] || (_cache[18] = [
                      _createTextVNode$2("上传精灵图", -1)
                    ])]),
                    _: 1
                  }),
                  _createVNode$2(_component_v_btn, { value: "url" }, {
                    default: _withCtx$2(() => [..._cache[19] || (_cache[19] = [
                      _createTextVNode$2("使用图片 URL", -1)
                    ])]),
                    _: 1
                  })
                ]),
                _: 1
              }, 8, ["modelValue", "disabled"])
            ], 64)) : _createCommentVNode$2("", true),
            imageMode.value === "upload" ? (_openBlock$2(), _createBlock$2(_component_v_file_input, {
              key: 1,
              modelValue: fileModel.value,
              "onUpdate:modelValue": [
                _cache[7] || (_cache[7] = ($event) => fileModel.value = $event),
                onImage
              ],
              label: "选择精灵图或 ZIP",
              accept: "image/png,image/webp,image/gif,image/jpeg,.zip",
              variant: "outlined",
              density: "compact",
              "prepend-icon": "",
              "prepend-inner-icon": "mdi-paperclip",
              "error-messages": imageError.value ? [imageError.value] : [],
              hint: "图片不超过 4MB，ZIP 不超过 8MB",
              "persistent-hint": "",
              disabled: submitting.value || codexImporting.value
            }, null, 8, ["modelValue", "error-messages", "disabled"])) : _createCommentVNode$2("", true),
            importMessage.value ? (_openBlock$2(), _createBlock$2(_component_v_alert, {
              key: 2,
              type: "success",
              variant: "tonal",
              density: "compact",
              class: "mt-3"
            }, {
              default: _withCtx$2(() => [
                _createTextVNode$2(_toDisplayString$2(validation.value?.pack?.name) + " · 已准备好，可以添加到我的素材。", 1)
              ]),
              _: 1
            })) : _createCommentVNode$2("", true),
            importMode.value === "codex" && packText.value ? (_openBlock$2(), _createBlock$2(_component_v_expansion_panels, {
              key: 3,
              variant: "accordion",
              class: "mt-3"
            }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_expansion_panel, { title: "编辑名称与动作映射" }, {
                  default: _withCtx$2(() => [
                    _createVNode$2(_component_v_expansion_panel_text, null, {
                      default: _withCtx$2(() => [
                        _createVNode$2(_component_v_textarea, {
                          modelValue: packText.value,
                          "onUpdate:modelValue": _cache[8] || (_cache[8] = ($event) => packText.value = $event),
                          label: "素材包 JSON",
                          rows: "6",
                          variant: "outlined",
                          density: "compact",
                          "hide-details": "",
                          class: "agent-pet-sprites-config__json",
                          disabled: submitting.value
                        }, null, 8, ["modelValue", "disabled"])
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })) : _createCommentVNode$2("", true),
            importError.value || clientErrors.value.length || serverError.value ? (_openBlock$2(), _createBlock$2(_component_v_alert, {
              key: 4,
              type: "error",
              variant: "tonal",
              density: "compact",
              class: "mt-3"
            }, {
              default: _withCtx$2(() => [
                (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2([
                  ...importError.value ? [importError.value] : [],
                  ...clientErrors.value,
                  ...serverError.value ? [serverError.value] : []
                ], (message) => {
                  return _openBlock$2(), _createElementBlock$2("div", { key: message }, _toDisplayString$2(message), 1);
                }), 128))
              ]),
              _: 1
            })) : _createCommentVNode$2("", true),
            _createElementVNode$2("div", _hoisted_11$2, [
              imageMode.value === "upload" ? (_openBlock$2(), _createBlock$2(_component_v_btn, {
                key: 0,
                color: "primary",
                variant: "tonal",
                "prepend-icon": "mdi-file-find-outline",
                loading: codexImporting.value,
                disabled: !selectedFile.value || !!imageError.value || codexImporting.value || submitting.value,
                onClick: importCodexPet
              }, {
                default: _withCtx$2(() => [..._cache[20] || (_cache[20] = [
                  _createTextVNode$2("读取 Codex Pet", -1)
                ])]),
                _: 1
              }, 8, ["loading", "disabled"])) : _createCommentVNode$2("", true),
              _createVNode$2(_component_v_btn, {
                color: "primary",
                variant: "flat",
                "prepend-icon": "mdi-plus",
                loading: submitting.value,
                disabled: !canSubmit.value || codexImporting.value,
                onClick: addPack
              }, {
                default: _withCtx$2(() => [..._cache[21] || (_cache[21] = [
                  _createTextVNode$2("添加 Pet", -1)
                ])]),
                _: 1
              }, 8, ["loading", "disabled"])
            ])
          ], 512), [
            [_vShow$1, importMode.value !== "archive"]
          ])
        ])
      ]);
    };
  }
});

const PackManager = /* @__PURE__ */ _export_sfc(_sfc_main$2, [["__scopeId", "data-v-6b56f482"]]);

function marketUrl(value) {
  if (!value) return "";
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : "";
  } catch {
    return "";
  }
}
function marketError(reason, fallback) {
  const response = reason?.response;
  if (response?.status === 403) return "仅管理员可以导入市场形象";
  const detail = response?.data?.detail ?? response?.data?.message;
  if (typeof detail === "string" && detail) return detail;
  return reason instanceof Error && reason.message ? reason.message : fallback;
}
function requireConnection(api, pluginId) {
  if (!api?.get || !api.post || !pluginId) throw new Error("页面连接尚未就绪，请重新打开");
  return api;
}
function record(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}
function isMarket(value) {
  return record(value) && typeof value.id === "string" && /^[a-z0-9_-]{1,32}$/.test(value.id) && typeof value.name === "string" && !!value.name.trim() && typeof value.description === "string" && (value.homepage === null || typeof value.homepage === "string");
}
function isItem(value) {
  return record(value) && typeof value.id === "string" && !!value.id && typeof value.name === "string" && !!value.name.trim() && ["description", "author", "license"].every((key) => typeof value[key] === "string") && ["preview", "source_url"].every((key) => value[key] === null || typeof value[key] === "string");
}
async function loadMarkets(api, pluginId) {
  const data = unwrap(await requireConnection(api, pluginId).get(`plugin/${pluginId}/markets`));
  if (!Array.isArray(data) || !data.every(isMarket) || new Set(data.map((item) => item.id)).size !== data.length) {
    throw new Error("市场列表响应无效，请刷新重试");
  }
  return data;
}
async function searchMarket(api, pluginId, marketId, keyword, page, pageSize = 12) {
  const query = new URLSearchParams({
    market_id: marketId,
    keyword: keyword.trim(),
    page: String(page),
    page_size: String(pageSize)
  });
  const data = unwrap(await requireConnection(api, pluginId).get(`plugin/${pluginId}/markets/items?${query}`));
  if (!record(data) || data.market_id !== marketId || data.page !== page || data.page_size !== pageSize || !Array.isArray(data.items) || !data.items.every(isItem) || data.items.length > pageSize || new Set(data.items.map((item) => item.id)).size !== data.items.length || !(data.total === null || Number.isInteger(data.total) && Number(data.total) >= data.items.length) || typeof data.has_more !== "boolean") {
    throw new Error("市场搜索响应无效，请重试");
  }
  return data;
}
async function importMarketPack(api, pluginId, marketId, itemId, mode) {
  const data = unwrap(
    await requireConnection(api, pluginId).post(`plugin/${pluginId}/markets/import`, {
      market_id: marketId,
      item_id: itemId,
      mode
    })
  );
  if (!record(data) || typeof data.id !== "string" || !/^[a-z0-9_-]{1,32}$/.test(data.id) || typeof data.name !== "string" || !data.name.trim()) {
    throw new Error("导入结果未确认，请刷新我的素材后核对");
  }
  return { id: data.id, name: data.name };
}

const {defineComponent:_defineComponent$1} = await importShared('vue');

const {resolveComponent:_resolveComponent$1,createVNode:_createVNode$1,withModifiers:_withModifiers,createElementVNode:_createElementVNode$1,toDisplayString:_toDisplayString$1,unref:_unref$1,createTextVNode:_createTextVNode$1,withCtx:_withCtx$1,openBlock:_openBlock$1,createBlock:_createBlock$1,createCommentVNode:_createCommentVNode$1,createElementBlock:_createElementBlock$1,renderList:_renderList$1,Fragment:_Fragment$1} = await importShared('vue');

const _hoisted_1$1 = {
  class: "ap-market",
  "aria-label": "在线形象市场"
};
const _hoisted_2$1 = { class: "ap-market__toolbar" };
const _hoisted_3$1 = {
  key: 0,
  class: "ap-market__source"
};
const _hoisted_4$1 = {
  key: 4,
  class: "ap-market__grid",
  "aria-label": "正在加载市场形象",
  "aria-busy": "true"
};
const _hoisted_5$1 = {
  key: 5,
  class: "ap-market__empty",
  role: "status"
};
const _hoisted_6$1 = {
  key: 6,
  class: "ap-market__empty",
  role: "status"
};
const _hoisted_7$1 = {
  key: 7,
  class: "ap-market__grid",
  role: "list",
  "aria-label": "市场形象"
};
const _hoisted_8$1 = ["aria-label", "disabled", "onClick"];
const _hoisted_9$1 = ["src", "alt", "onError"];
const _hoisted_10$1 = { class: "ap-market__item-body" };
const _hoisted_11$1 = ["title"];
const _hoisted_12$1 = { class: "ap-market__author" };
const _hoisted_13$1 = ["title"];
const _hoisted_14$1 = { class: "ap-market__item-actions" };
const _hoisted_15$1 = {
  key: 8,
  class: "ap-market__pagination",
  "aria-label": "市场分页"
};
const _hoisted_16$1 = { role: "status" };
const _hoisted_17$1 = { class: "ap-market__review-preview" };
const _hoisted_18$1 = ["src", "alt"];
const _hoisted_19$1 = { class: "ap-market__review-description" };
const _hoisted_20$1 = { class: "ap-market__metadata" };
const {computed: computed$1,inject: inject$1,onBeforeUnmount: onBeforeUnmount$1,ref: ref$1,watch: watch$1} = await importShared('vue');
const _sfc_main$1 = /* @__PURE__ */ _defineComponent$1({
  __name: "MarketBrowser",
  props: {
    api: { default: null },
    pluginId: { default: "" }
  },
  emits: ["imported"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const toast = inject$1("moviepilot:toast", null);
    const markets = ref$1([]);
    const marketId = ref$1("");
    const keyword = ref$1("");
    const submittedKeyword = ref$1("");
    const result = ref$1(null);
    const page = ref$1(1);
    const listLoading = ref$1(false);
    const loading = ref$1(false);
    const listError = ref$1("");
    const error = ref$1("");
    const notice = ref$1("");
    const failedImages = ref$1(/* @__PURE__ */ new Set());
    const selected = ref$1(null);
    const mode = ref$1("new");
    const importing = ref$1(false);
    const importError = ref$1("");
    const importedIds = ref$1(/* @__PURE__ */ new Set());
    const market = computed$1(() => markets.value.find((item) => item.id === marketId.value));
    const pageCount = computed$1(
      () => result.value?.total === null ? null : Math.max(1, Math.ceil((result.value?.total ?? 0) / 12))
    );
    let alive = true;
    let scopeVersion = 0;
    let queryVersion = 0;
    function imageFailed(item) {
      failedImages.value = /* @__PURE__ */ new Set([...failedImages.value, item.id]);
    }
    function preview(item) {
      return failedImages.value.has(item.id) ? "" : marketUrl(item.preview);
    }
    async function fetchPage(nextPage = 1) {
      if (!marketId.value) return;
      const version = ++queryVersion;
      const scope = scopeVersion;
      const id = props.pluginId;
      const target = marketId.value;
      page.value = nextPage;
      result.value = null;
      error.value = "";
      failedImages.value = /* @__PURE__ */ new Set();
      loading.value = true;
      try {
        const data = await searchMarket(props.api, id, target, submittedKeyword.value, nextPage);
        if (!alive || scope !== scopeVersion || version !== queryVersion) return;
        result.value = data;
      } catch (reason) {
        if (alive && scope === scopeVersion && version === queryVersion)
          error.value = marketError(reason, "市场暂时无法读取，请重试");
      } finally {
        if (alive && scope === scopeVersion && version === queryVersion) loading.value = false;
      }
    }
    async function initialize() {
      const scope = ++scopeVersion;
      queryVersion++;
      markets.value = [];
      marketId.value = "";
      keyword.value = "";
      submittedKeyword.value = "";
      result.value = null;
      selected.value = null;
      failedImages.value = /* @__PURE__ */ new Set();
      importing.value = false;
      loading.value = false;
      listError.value = "";
      error.value = "";
      notice.value = "";
      importError.value = "";
      importedIds.value = /* @__PURE__ */ new Set();
      listLoading.value = true;
      try {
        const data = await loadMarkets(props.api, props.pluginId);
        if (!alive || scope !== scopeVersion) return;
        markets.value = data;
        marketId.value = data[0]?.id ?? "";
        if (marketId.value) void fetchPage();
      } catch (reason) {
        if (alive && scope === scopeVersion) listError.value = marketError(reason, "市场列表读取失败，请重试");
      } finally {
        if (alive && scope === scopeVersion) listLoading.value = false;
      }
    }
    function changeMarket(value) {
      if (importing.value) return;
      marketId.value = value;
      keyword.value = "";
      submittedKeyword.value = "";
      selected.value = null;
      notice.value = "";
      void fetchPage();
    }
    function search() {
      if (importing.value || !marketId.value) return;
      submittedKeyword.value = (keyword.value ?? "").trim();
      void fetchPage();
    }
    function clearSearch() {
      keyword.value = "";
      search();
    }
    function choose(item) {
      selected.value = item;
      mode.value = importedIds.value.has(`${marketId.value}:${item.id}`) ? "copy" : "new";
      importError.value = "";
    }
    function closeReview(value) {
      if (!value && !importing.value) selected.value = null;
    }
    async function importSelected() {
      if (!selected.value || importing.value) return;
      const item = selected.value;
      const scope = scopeVersion;
      const target = marketId.value;
      const id = props.pluginId;
      importing.value = true;
      importError.value = "";
      try {
        const saved = await importMarketPack(props.api, id, target, item.id, mode.value);
        if (!alive || scope !== scopeVersion) return;
        importedIds.value = /* @__PURE__ */ new Set([...importedIds.value, `${target}:${item.id}`]);
        notice.value = `已导入 ${saved.name}`;
        selected.value = null;
        toast?.success?.(notice.value);
        emit("imported");
      } catch (reason) {
        if (alive && scope === scopeVersion) importError.value = marketError(reason, "导入未完成，请刷新我的素材核对后重试");
      } finally {
        if (alive && scope === scopeVersion) importing.value = false;
      }
    }
    watch$1([() => props.pluginId, () => props.api], () => void initialize(), { immediate: true });
    onBeforeUnmount$1(() => {
      alive = false;
      scopeVersion++;
      queryVersion++;
    });
    return (_ctx, _cache) => {
      const _component_v_select = _resolveComponent$1("v-select");
      const _component_v_text_field = _resolveComponent$1("v-text-field");
      const _component_v_btn = _resolveComponent$1("v-btn");
      const _component_v_alert = _resolveComponent$1("v-alert");
      const _component_v_skeleton_loader = _resolveComponent$1("v-skeleton-loader");
      const _component_v_icon = _resolveComponent$1("v-icon");
      const _component_v_chip = _resolveComponent$1("v-chip");
      const _component_v_spacer = _resolveComponent$1("v-spacer");
      const _component_v_radio = _resolveComponent$1("v-radio");
      const _component_v_radio_group = _resolveComponent$1("v-radio-group");
      const _component_v_card_text = _resolveComponent$1("v-card-text");
      const _component_v_card_actions = _resolveComponent$1("v-card-actions");
      const _component_v_card = _resolveComponent$1("v-card");
      const _component_v_dialog = _resolveComponent$1("v-dialog");
      return _openBlock$1(), _createElementBlock$1("section", _hoisted_1$1, [
        _createElementVNode$1("div", _hoisted_2$1, [
          _createVNode$1(_component_v_select, {
            "model-value": marketId.value,
            items: markets.value,
            "item-title": "name",
            "item-value": "id",
            label: "形象市场",
            "aria-label": "形象市场",
            variant: "outlined",
            density: "compact",
            "hide-details": "",
            loading: listLoading.value,
            disabled: listLoading.value || !markets.value.length || importing.value,
            "onUpdate:modelValue": changeMarket
          }, null, 8, ["model-value", "items", "loading", "disabled"]),
          _createElementVNode$1("form", {
            class: "ap-market__search",
            onSubmit: _withModifiers(search, ["prevent"])
          }, [
            _createVNode$1(_component_v_text_field, {
              modelValue: keyword.value,
              "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => keyword.value = $event),
              label: "搜索形象",
              maxlength: "200",
              variant: "outlined",
              density: "compact",
              "hide-details": "",
              clearable: "",
              disabled: !marketId.value || importing.value,
              "onClick:clear": clearSearch
            }, null, 8, ["modelValue", "disabled"]),
            _createVNode$1(_component_v_btn, {
              type: "submit",
              color: "primary",
              variant: "tonal",
              icon: "mdi-magnify",
              "aria-label": "搜索市场形象",
              disabled: !marketId.value || importing.value
            }, null, 8, ["disabled"])
          ], 32)
        ]),
        market.value ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_3$1, [
          _createElementVNode$1("span", null, _toDisplayString$1(market.value.description), 1),
          _unref$1(marketUrl)(market.value.homepage) ? (_openBlock$1(), _createBlock$1(_component_v_btn, {
            key: 0,
            href: _unref$1(marketUrl)(market.value.homepage),
            target: "_blank",
            rel: "noopener noreferrer",
            size: "small",
            variant: "text",
            "append-icon": "mdi-open-in-new"
          }, {
            default: _withCtx$1(() => [..._cache[7] || (_cache[7] = [
              _createTextVNode$1("市场主页", -1)
            ])]),
            _: 1
          }, 8, ["href"])) : _createCommentVNode$1("", true)
        ])) : _createCommentVNode$1("", true),
        notice.value ? (_openBlock$1(), _createBlock$1(_component_v_alert, {
          key: 1,
          role: "status",
          type: "success",
          variant: "tonal",
          density: "compact",
          class: "mb-4"
        }, {
          default: _withCtx$1(() => [
            _createTextVNode$1(_toDisplayString$1(notice.value), 1)
          ]),
          _: 1
        })) : _createCommentVNode$1("", true),
        listError.value || error.value ? (_openBlock$1(), _createBlock$1(_component_v_alert, {
          key: 2,
          role: "alert",
          type: "error",
          variant: "tonal",
          density: "compact",
          class: "mb-4"
        }, {
          append: _withCtx$1(() => [
            _createVNode$1(_component_v_btn, {
              size: "small",
              variant: "text",
              "prepend-icon": "mdi-refresh",
              onClick: _cache[1] || (_cache[1] = ($event) => listError.value ? initialize() : fetchPage(page.value))
            }, {
              default: _withCtx$1(() => [..._cache[8] || (_cache[8] = [
                _createTextVNode$1("重试", -1)
              ])]),
              _: 1
            })
          ]),
          default: _withCtx$1(() => [
            _createTextVNode$1(_toDisplayString$1(listError.value || error.value) + " ", 1)
          ]),
          _: 1
        })) : _createCommentVNode$1("", true),
        failedImages.value.size ? (_openBlock$1(), _createBlock$1(_component_v_alert, {
          key: 3,
          role: "status",
          type: "info",
          variant: "tonal",
          density: "compact",
          class: "mb-4"
        }, {
          default: _withCtx$1(() => [..._cache[9] || (_cache[9] = [
            _createTextVNode$1(" 部分预览图加载失败。图片由浏览器直接加载，请打开原图检查浏览器网络；MoviePilot 图片安全域不影响此处。 ", -1)
          ])]),
          _: 1
        })) : _createCommentVNode$1("", true),
        listLoading.value || loading.value ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_4$1, [
          (_openBlock$1(), _createElementBlock$1(_Fragment$1, null, _renderList$1(6, (index) => {
            return _createElementVNode$1("div", {
              key: index,
              class: "ap-market__skeleton"
            }, [
              _createVNode$1(_component_v_skeleton_loader, { type: "image, list-item-two-line" })
            ]);
          }), 64))
        ])) : !listError.value && !markets.value.length ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_5$1, [
          _createVNode$1(_component_v_icon, {
            icon: "mdi-storefront-outline",
            size: "36"
          }),
          _cache[10] || (_cache[10] = _createElementVNode$1("p", null, "暂未接入形象市场", -1))
        ])) : result.value && !result.value.items.length ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_6$1, [
          _createVNode$1(_component_v_icon, {
            icon: "mdi-magnify",
            size: "36"
          }),
          _createElementVNode$1("p", null, _toDisplayString$1(submittedKeyword.value ? "没有找到匹配的形象" : "当前市场暂无形象"), 1)
        ])) : result.value ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_7$1, [
          (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(result.value.items, (item) => {
            return _openBlock$1(), _createElementBlock$1("article", {
              key: item.id,
              class: "ap-market__item",
              role: "listitem"
            }, [
              _createElementVNode$1("button", {
                class: "ap-market__preview",
                type: "button",
                "aria-label": `预览 ${item.name}`,
                disabled: importing.value,
                onClick: ($event) => choose(item)
              }, [
                preview(item) ? (_openBlock$1(), _createElementBlock$1("img", {
                  key: 0,
                  src: preview(item),
                  alt: item.name,
                  loading: "lazy",
                  referrerpolicy: "no-referrer",
                  onError: ($event) => imageFailed(item)
                }, null, 40, _hoisted_9$1)) : (_openBlock$1(), _createBlock$1(_component_v_icon, {
                  key: 1,
                  icon: "mdi-paw-outline",
                  size: "38",
                  "aria-hidden": "true"
                }))
              ], 8, _hoisted_8$1),
              _createElementVNode$1("div", _hoisted_10$1, [
                _createElementVNode$1("h3", {
                  title: item.name
                }, _toDisplayString$1(item.name), 9, _hoisted_11$1),
                _createElementVNode$1("p", _hoisted_12$1, _toDisplayString$1(item.author || "作者未提供"), 1),
                _createElementVNode$1("p", {
                  class: "ap-market__description",
                  title: item.description
                }, _toDisplayString$1(item.description || "暂无说明"), 9, _hoisted_13$1),
                failedImages.value.has(item.id) && _unref$1(marketUrl)(item.preview) ? (_openBlock$1(), _createBlock$1(_component_v_btn, {
                  key: 0,
                  href: _unref$1(marketUrl)(item.preview),
                  "aria-label": `查看 ${item.name} 原图`,
                  target: "_blank",
                  rel: "noopener noreferrer",
                  size: "small",
                  variant: "text",
                  "append-icon": "mdi-open-in-new"
                }, {
                  default: _withCtx$1(() => [..._cache[11] || (_cache[11] = [
                    _createTextVNode$1("查看原图", -1)
                  ])]),
                  _: 1
                }, 8, ["href", "aria-label"])) : _createCommentVNode$1("", true),
                _createElementVNode$1("div", _hoisted_14$1, [
                  importedIds.value.has(`${marketId.value}:${item.id}`) ? (_openBlock$1(), _createBlock$1(_component_v_chip, {
                    key: 0,
                    size: "x-small",
                    color: "success",
                    variant: "tonal"
                  }, {
                    default: _withCtx$1(() => [..._cache[12] || (_cache[12] = [
                      _createTextVNode$1("已导入", -1)
                    ])]),
                    _: 1
                  })) : _createCommentVNode$1("", true),
                  _createVNode$1(_component_v_spacer),
                  _createVNode$1(_component_v_btn, {
                    size: "small",
                    variant: "tonal",
                    color: "primary",
                    "prepend-icon": "mdi-download-outline",
                    "aria-label": `导入 ${item.name}`,
                    disabled: importing.value,
                    onClick: ($event) => choose(item)
                  }, {
                    default: _withCtx$1(() => [..._cache[13] || (_cache[13] = [
                      _createTextVNode$1("导入", -1)
                    ])]),
                    _: 1
                  }, 8, ["aria-label", "disabled", "onClick"])
                ])
              ])
            ]);
          }), 128))
        ])) : _createCommentVNode$1("", true),
        result.value ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_15$1, [
          _createElementVNode$1("span", _hoisted_16$1, _toDisplayString$1(result.value.total === null ? "总量未知" : `共 ${result.value.total} 个形象`) + " · 第 " + _toDisplayString$1(page.value) + " 页" + _toDisplayString$1(pageCount.value ? ` / ${pageCount.value}` : ""), 1),
          _createElementVNode$1("div", null, [
            _createVNode$1(_component_v_btn, {
              icon: "mdi-chevron-left",
              "aria-label": "上一页",
              variant: "text",
              size: "small",
              disabled: page.value <= 1 || loading.value || importing.value,
              onClick: _cache[2] || (_cache[2] = ($event) => fetchPage(page.value - 1))
            }, null, 8, ["disabled"]),
            _createVNode$1(_component_v_btn, {
              icon: "mdi-chevron-right",
              "aria-label": "下一页",
              variant: "text",
              size: "small",
              disabled: !result.value.has_more || loading.value || importing.value,
              onClick: _cache[3] || (_cache[3] = ($event) => fetchPage(page.value + 1))
            }, null, 8, ["disabled"])
          ])
        ])) : _createCommentVNode$1("", true),
        _createVNode$1(_component_v_dialog, {
          "model-value": !!selected.value,
          "max-width": "580",
          persistent: importing.value,
          "onUpdate:modelValue": closeReview
        }, {
          default: _withCtx$1(() => [
            selected.value ? (_openBlock$1(), _createBlock$1(_component_v_card, {
              key: 0,
              title: selected.value.name
            }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_card_text, null, {
                  default: _withCtx$1(() => [
                    _createElementVNode$1("div", _hoisted_17$1, [
                      preview(selected.value) ? (_openBlock$1(), _createElementBlock$1("img", {
                        key: 0,
                        src: preview(selected.value),
                        alt: selected.value.name,
                        referrerpolicy: "no-referrer",
                        onError: _cache[4] || (_cache[4] = ($event) => imageFailed(selected.value))
                      }, null, 40, _hoisted_18$1)) : (_openBlock$1(), _createBlock$1(_component_v_icon, {
                        key: 1,
                        icon: "mdi-paw-outline",
                        size: "60"
                      }))
                    ]),
                    failedImages.value.has(selected.value.id) ? (_openBlock$1(), _createBlock$1(_component_v_alert, {
                      key: 0,
                      role: "status",
                      type: "info",
                      variant: "tonal",
                      density: "compact",
                      class: "mt-3"
                    }, {
                      default: _withCtx$1(() => [
                        _cache[15] || (_cache[15] = _createTextVNode$1(" 浏览器无法加载预览图，不影响尝试导入。 ", -1)),
                        _unref$1(marketUrl)(selected.value.preview) ? (_openBlock$1(), _createBlock$1(_component_v_btn, {
                          key: 0,
                          href: _unref$1(marketUrl)(selected.value.preview),
                          "aria-label": `查看 ${selected.value.name} 原图`,
                          target: "_blank",
                          rel: "noopener noreferrer",
                          size: "small",
                          variant: "text",
                          "append-icon": "mdi-open-in-new"
                        }, {
                          default: _withCtx$1(() => [..._cache[14] || (_cache[14] = [
                            _createTextVNode$1("查看原图", -1)
                          ])]),
                          _: 1
                        }, 8, ["href", "aria-label"])) : _createCommentVNode$1("", true)
                      ]),
                      _: 1
                    })) : _createCommentVNode$1("", true),
                    _createElementVNode$1("p", _hoisted_19$1, _toDisplayString$1(selected.value.description || "暂无说明"), 1),
                    _createElementVNode$1("dl", _hoisted_20$1, [
                      _cache[16] || (_cache[16] = _createElementVNode$1("dt", null, "市场", -1)),
                      _createElementVNode$1("dd", null, _toDisplayString$1(market.value?.name), 1),
                      _cache[17] || (_cache[17] = _createElementVNode$1("dt", null, "作者", -1)),
                      _createElementVNode$1("dd", null, _toDisplayString$1(selected.value.author || "未提供"), 1),
                      _cache[18] || (_cache[18] = _createElementVNode$1("dt", null, "许可", -1)),
                      _createElementVNode$1("dd", null, _toDisplayString$1(selected.value.license || "未提供"), 1)
                    ]),
                    _unref$1(marketUrl)(selected.value.source_url) ? (_openBlock$1(), _createBlock$1(_component_v_btn, {
                      key: 1,
                      href: _unref$1(marketUrl)(selected.value.source_url),
                      target: "_blank",
                      rel: "noopener noreferrer",
                      size: "small",
                      variant: "text",
                      "append-icon": "mdi-open-in-new",
                      class: "mb-3"
                    }, {
                      default: _withCtx$1(() => [..._cache[19] || (_cache[19] = [
                        _createTextVNode$1("查看来源", -1)
                      ])]),
                      _: 1
                    }, 8, ["href"])) : _createCommentVNode$1("", true),
                    _createVNode$1(_component_v_radio_group, {
                      modelValue: mode.value,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = ($event) => mode.value = $event),
                      label: "导入方式",
                      disabled: importing.value,
                      "hide-details": ""
                    }, {
                      default: _withCtx$1(() => [
                        _createVNode$1(_component_v_radio, {
                          label: "新增素材",
                          value: "new"
                        }),
                        _createVNode$1(_component_v_radio, {
                          label: "导入副本",
                          value: "copy"
                        })
                      ]),
                      _: 1
                    }, 8, ["modelValue", "disabled"]),
                    importError.value ? (_openBlock$1(), _createBlock$1(_component_v_alert, {
                      key: 2,
                      role: "alert",
                      type: "error",
                      variant: "tonal",
                      density: "compact",
                      class: "mt-3"
                    }, {
                      default: _withCtx$1(() => [
                        _createTextVNode$1(_toDisplayString$1(importError.value), 1)
                      ]),
                      _: 1
                    })) : _createCommentVNode$1("", true)
                  ]),
                  _: 1
                }),
                _createVNode$1(_component_v_card_actions, null, {
                  default: _withCtx$1(() => [
                    _createVNode$1(_component_v_spacer),
                    _createVNode$1(_component_v_btn, {
                      disabled: importing.value,
                      onClick: _cache[6] || (_cache[6] = ($event) => selected.value = null)
                    }, {
                      default: _withCtx$1(() => [..._cache[20] || (_cache[20] = [
                        _createTextVNode$1("取消", -1)
                      ])]),
                      _: 1
                    }, 8, ["disabled"]),
                    _createVNode$1(_component_v_btn, {
                      color: "primary",
                      variant: "flat",
                      "prepend-icon": "mdi-download-outline",
                      loading: importing.value,
                      disabled: importing.value,
                      onClick: importSelected
                    }, {
                      default: _withCtx$1(() => [..._cache[21] || (_cache[21] = [
                        _createTextVNode$1("确认导入", -1)
                      ])]),
                      _: 1
                    }, 8, ["loading", "disabled"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }, 8, ["title"])) : _createCommentVNode$1("", true)
          ]),
          _: 1
        }, 8, ["model-value", "persistent"])
      ]);
    };
  }
});

const MarketBrowser = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-f1fcaa54"]]);

const {defineComponent:_defineComponent} = await importShared('vue');

const {unref:_unref,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,renderList:_renderList,Fragment:_Fragment,createBlock:_createBlock,vShow:_vShow,withDirectives:_withDirectives,normalizeClass:_normalizeClass} = await importShared('vue');

const _hoisted_1 = {
  class: "ap-config",
  "data-agentpets-editor": ""
};
const _hoisted_2 = { class: "ap-shell" };
const _hoisted_3 = { class: "ap-header" };
const _hoisted_4 = { class: "ap-brand" };
const _hoisted_5 = ["src"];
const _hoisted_6 = {
  key: 1,
  class: "ap-brand__avatar d-flex align-center justify-center",
  "aria-hidden": "true"
};
const _hoisted_7 = { class: "ap-config__body" };
const _hoisted_8 = {
  class: "ap-nav",
  "aria-label": "配置分组"
};
const _hoisted_9 = { class: "ap-section-heading" };
const _hoisted_10 = { class: "ap-flow" };
const _hoisted_11 = { class: "ap-flow__step" };
const _hoisted_12 = { class: "ap-flow__step" };
const _hoisted_13 = { class: "ap-flow__step" };
const _hoisted_14 = { class: "ap-flow__step" };
const _hoisted_15 = { class: "ap-inline" };
const _hoisted_16 = { class: "ap-metrics" };
const _hoisted_17 = { class: "ap-metric" };
const _hoisted_18 = { class: "ap-metric" };
const _hoisted_19 = { class: "ap-metric" };
const _hoisted_20 = { class: "ap-note" };
const _hoisted_21 = { class: "ap-setting-row" };
const _hoisted_22 = { class: "ap-footer" };
const _hoisted_23 = {
  key: 0,
  class: "ap-change",
  role: "status"
};
const _hoisted_24 = {
  key: 1,
  class: "ap-muted"
};
const _hoisted_25 = { class: "ap-footer__actions" };
const {computed,inject,onBeforeUnmount,ref,watch} = await importShared('vue');
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Config",
  props: {
    initialConfig: { default: null },
    api: { default: null },
    pluginId: { default: "" },
    sourcePluginId: { default: "" }
  },
  emits: ["save", "close", "switch", "layout"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    emit("layout", { maxWidth: "72rem" });
    const agent = inject(AGENT_HOST_KEY, null);
    const activeMain = ref("overview");
    const visitedPacks = ref(false);
    const visitedMarket = ref(false);
    const packManager = ref(null);
    const enabled = ref(Boolean(props.initialConfig?.enabled));
    const baseline = ref(Boolean(props.initialConfig?.enabled));
    const changed = computed(() => enabled.value !== baseline.value);
    const snapshot = ref(null);
    const loading = ref(false);
    const saving = ref(false);
    const saveError = ref("");
    const error = ref("");
    const avatar = builtinAvatar("ying");
    const avatarFailed = ref(false);
    const groups = [
      {
        key: "overview",
        title: "运行总览",
        icon: "mdi-view-dashboard-outline",
        description: "从准备形象到正式使用，状态一目了然。"
      },
      { key: "basic", title: "基础设置", icon: "mdi-tune-variant", description: "设置插件开关，调整形象请前往详情页。" },
      {
        key: "packs",
        title: "素材管理",
        icon: "mdi-package-variant-closed",
        description: "导入你的 Pet，或管理已有的素材包。"
      },
      { key: "market", title: "在线市场", icon: "mdi-storefront-outline", description: "" }
    ];
    const group = computed(() => groups.find((item) => item.key === activeMain.value) ?? groups[0]);
    const stageCount = computed(() => snapshot.value?.pets.filter((pet) => pet.mode === "stage").length ?? 0);
    let disposed = false;
    let requestVersion = 0;
    let draftInstance = props.pluginId;
    watch(
      [() => props.pluginId, () => props.initialConfig],
      ([id, value]) => {
        const incoming = Boolean(value?.enabled);
        if (id !== draftInstance || !changed.value || incoming === enabled.value) {
          enabled.value = incoming;
          baseline.value = incoming;
          draftInstance = id;
        }
      },
      { deep: true }
    );
    watch(activeMain, (value) => {
      if (value === "packs") visitedPacks.value = true;
      if (value === "market") visitedMarket.value = true;
    });
    function marketImported() {
      void refresh();
      void packManager.value?.refresh();
    }
    async function refresh() {
      const version = ++requestVersion;
      const id = props.pluginId;
      loading.value = true;
      error.value = "";
      try {
        const result = await loadEditor(props.api, id);
        if (disposed || version !== requestVersion || id !== props.pluginId) return;
        snapshot.value = result;
      } catch {
        if (!disposed && version === requestVersion) error.value = "运行状态暂时无法读取，可刷新重试。";
      } finally {
        if (!disposed && version === requestVersion) loading.value = false;
      }
    }
    watch(
      () => props.pluginId,
      () => {
        snapshot.value = null;
        saving.value = false;
        saveError.value = "";
        void refresh();
      },
      { immediate: true }
    );
    onBeforeUnmount(() => {
      disposed = true;
      requestVersion++;
    });
    async function save() {
      if (saving.value || !changed.value) return;
      const id = props.pluginId;
      saving.value = true;
      saveError.value = "";
      try {
        const config = await prepareEnabledConfig(props.api, id, enabled.value, baseline.value);
        if (!disposed && id === props.pluginId) emit("save", config);
      } catch (reason) {
        if (!disposed && id === props.pluginId)
          saveError.value = reason instanceof Error ? reason.message : "无法读取最新配置，未提交修改，请重试";
      } finally {
        if (!disposed && id === props.pluginId) saving.value = false;
      }
    }
    return (_ctx, _cache) => {
      const _component_v_icon = _resolveComponent("v-icon");
      const _component_v_chip = _resolveComponent("v-chip");
      const _component_v_btn = _resolveComponent("v-btn");
      const _component_v_list_item = _resolveComponent("v-list-item");
      const _component_v_list = _resolveComponent("v-list");
      const _component_v_alert = _resolveComponent("v-alert");
      const _component_v_spacer = _resolveComponent("v-spacer");
      const _component_v_switch = _resolveComponent("v-switch");
      const _component_v_card_item = _resolveComponent("v-card-item");
      const _component_v_card = _resolveComponent("v-card");
      return _openBlock(), _createElementBlock("section", _hoisted_1, [
        _createElementVNode("div", _hoisted_2, [
          _createElementVNode("header", _hoisted_3, [
            _createElementVNode("div", _hoisted_4, [
              !avatarFailed.value ? (_openBlock(), _createElementBlock("img", {
                key: 0,
                src: _unref(avatar),
                alt: "",
                class: "ap-brand__avatar",
                onError: _cache[0] || (_cache[0] = ($event) => avatarFailed.value = true)
              }, null, 40, _hoisted_5)) : (_openBlock(), _createElementBlock("span", _hoisted_6, [
                _createVNode(_component_v_icon, {
                  icon: "mdi-paw-outline",
                  color: "primary",
                  size: "28"
                })
              ])),
              _cache[6] || (_cache[6] = _createElementVNode("div", null, [
                _createElementVNode("div", { class: "ap-eyebrow" }, "MoviePilot / 插件设置"),
                _createElementVNode("h1", null, "助手形象")
              ], -1)),
              _createVNode(_component_v_chip, {
                color: snapshot.value?.enabled ? "success" : "default",
                size: "x-small",
                variant: "tonal"
              }, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(snapshot.value ? snapshot.value.enabled ? "运行中" : "未启用" : "待读取"), 1)
                ]),
                _: 1
              }, 8, ["color"])
            ]),
            _createVNode(_component_v_btn, {
              class: "ap-header__close",
              icon: "mdi-close",
              "aria-label": "关闭配置页",
              variant: "text",
              size: "small",
              onClick: _cache[1] || (_cache[1] = ($event) => emit("close"))
            })
          ]),
          _createElementVNode("div", _hoisted_7, [
            _createElementVNode("nav", _hoisted_8, [
              _cache[7] || (_cache[7] = _createElementVNode("div", { class: "ap-nav__label" }, "PET 设置", -1)),
              _createVNode(_component_v_list, {
                density: "compact",
                nav: ""
              }, {
                default: _withCtx(() => [
                  (_openBlock(), _createElementBlock(_Fragment, null, _renderList(groups, (item) => {
                    return _createVNode(_component_v_list_item, {
                      key: item.key,
                      active: activeMain.value === item.key,
                      "prepend-icon": item.icon,
                      title: item.title,
                      color: "primary",
                      rounded: "lg",
                      onClick: ($event) => activeMain.value = item.key
                    }, null, 8, ["active", "prepend-icon", "title", "onClick"]);
                  }), 64))
                ]),
                _: 1
              })
            ]),
            _createElementVNode("main", {
              class: _normalizeClass(["ap-pane", { "ap-pane--overview": activeMain.value === "overview" }])
            }, [
              _createElementVNode("div", _hoisted_9, [
                _createVNode(_component_v_icon, {
                  icon: group.value.icon,
                  color: "primary",
                  size: "22"
                }, null, 8, ["icon"]),
                _createElementVNode("div", null, [
                  _createElementVNode("h2", null, _toDisplayString(group.value.title), 1),
                  _createElementVNode("p", null, _toDisplayString(group.value.description), 1)
                ])
              ]),
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
              saveError.value ? (_openBlock(), _createBlock(_component_v_alert, {
                key: 1,
                type: "error",
                variant: "tonal",
                density: "compact",
                class: "mb-4"
              }, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(saveError.value), 1)
                ]),
                _: 1
              })) : _createCommentVNode("", true),
              activeMain.value === "overview" ? (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                _cache[22] || (_cache[22] = _createElementVNode("h3", { class: "ap-section-title" }, "从形象到陪伴", -1)),
                _createElementVNode("div", _hoisted_10, [
                  _createElementVNode("div", _hoisted_11, [
                    _createVNode(_component_v_icon, {
                      icon: "mdi-power",
                      color: "primary"
                    }),
                    _cache[8] || (_cache[8] = _createElementVNode("strong", null, "启用插件", -1)),
                    _cache[9] || (_cache[9] = _createElementVNode("span", { class: "ap-muted" }, "让 MP 发现可选形象", -1))
                  ]),
                  _createElementVNode("div", _hoisted_12, [
                    _createVNode(_component_v_icon, {
                      icon: "mdi-package-down",
                      color: "primary"
                    }),
                    _cache[10] || (_cache[10] = _createElementVNode("strong", null, "准备 Pet", -1)),
                    _cache[11] || (_cache[11] = _createElementVNode("span", { class: "ap-muted" }, "使用内置或导入素材", -1))
                  ]),
                  _createElementVNode("div", _hoisted_13, [
                    _createVNode(_component_v_icon, {
                      icon: "mdi-tune",
                      color: "primary"
                    }),
                    _cache[12] || (_cache[12] = _createElementVNode("strong", null, "调整预览", -1)),
                    _cache[13] || (_cache[13] = _createElementVNode("span", { class: "ap-muted" }, "在详情页边调边看", -1))
                  ]),
                  _createElementVNode("div", _hoisted_14, [
                    _createVNode(_component_v_icon, {
                      icon: "mdi-check-circle-outline",
                      color: "primary"
                    }),
                    _cache[14] || (_cache[14] = _createElementVNode("strong", null, "选择形象", -1)),
                    _cache[15] || (_cache[15] = _createElementVNode("span", { class: "ap-muted" }, "在 MP 设置中选择", -1))
                  ])
                ]),
                _createElementVNode("div", _hoisted_15, [
                  _cache[16] || (_cache[16] = _createElementVNode("h3", { class: "ap-section-title mb-0" }, "当前状态", -1)),
                  _createVNode(_component_v_spacer),
                  _createVNode(_component_v_btn, {
                    icon: "mdi-refresh",
                    "aria-label": "刷新运行状态",
                    variant: "text",
                    size: "small",
                    loading: loading.value,
                    onClick: refresh
                  }, null, 8, ["loading"])
                ]),
                error.value ? (_openBlock(), _createBlock(_component_v_alert, {
                  key: 0,
                  type: "warning",
                  variant: "tonal",
                  density: "compact"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(error.value), 1)
                  ]),
                  _: 1
                })) : _createCommentVNode("", true),
                _createElementVNode("div", _hoisted_16, [
                  _createElementVNode("div", _hoisted_17, [
                    _cache[17] || (_cache[17] = _createElementVNode("span", { class: "ap-muted" }, "可选 Pet", -1)),
                    _createElementVNode("strong", null, _toDisplayString(snapshot.value?.pets.length ?? "—"), 1)
                  ]),
                  _createElementVNode("div", _hoisted_18, [
                    _cache[18] || (_cache[18] = _createElementVNode("span", { class: "ap-muted" }, "自由活动", -1)),
                    _createElementVNode("strong", null, _toDisplayString(snapshot.value ? stageCount.value : "—"), 1)
                  ]),
                  _createElementVNode("div", _hoisted_19, [
                    _cache[19] || (_cache[19] = _createElementVNode("span", { class: "ap-muted" }, "入口形象", -1)),
                    _createElementVNode("strong", null, _toDisplayString(snapshot.value ? snapshot.value.pets.length - stageCount.value : "—"), 1)
                  ])
                ]),
                _createElementVNode("div", _hoisted_20, [
                  _createVNode(_component_v_icon, {
                    icon: "mdi-information-outline",
                    color: "primary",
                    size: "18"
                  }),
                  _cache[20] || (_cache[20] = _createElementVNode("div", null, [
                    _createTextVNode(" 插件没有后台任务。素材暂时不可用时，MP 会回退到内置形象；检查素材并重新选择即可。"),
                    _createElementVNode("br"),
                    _createTextVNode("当前配置页管理开关和素材，Pet 的大小、活动与实时预览集中在详情页。 ")
                  ], -1))
                ]),
                _createVNode(_component_v_btn, {
                  class: "mt-4",
                  color: "primary",
                  variant: "tonal",
                  "prepend-icon": "mdi-paw-outline",
                  onClick: _cache[2] || (_cache[2] = ($event) => emit("switch"))
                }, {
                  default: _withCtx(() => [..._cache[21] || (_cache[21] = [
                    _createTextVNode("前往调整与预览", -1)
                  ])]),
                  _: 1
                })
              ], 64)) : _createCommentVNode("", true),
              activeMain.value === "basic" ? (_openBlock(), _createElementBlock(_Fragment, { key: 3 }, [
                _createVNode(_component_v_card, {
                  variant: "outlined",
                  class: "mb-4",
                  style: { "background": "transparent" }
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_card_item, {
                      title: "启用助手形象",
                      subtitle: "启用后，内置与导入的 Pet 会出现在 MP 的助手形象列表中。"
                    }, {
                      append: _withCtx(() => [
                        _createVNode(_component_v_switch, {
                          modelValue: enabled.value,
                          "onUpdate:modelValue": _cache[3] || (_cache[3] = ($event) => enabled.value = $event),
                          disabled: saving.value,
                          "aria-label": "启用助手形象",
                          color: "success",
                          inset: "",
                          "hide-details": "",
                          density: "compact"
                        }, null, 8, ["modelValue", "disabled"])
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createElementVNode("div", _hoisted_21, [
                  _cache[24] || (_cache[24] = _createElementVNode("h3", null, "形象调整", -1)),
                  _cache[25] || (_cache[25] = _createElementVNode("p", { class: "ap-muted" }, "角色大小、移动速度和活动范围在详情页统一调整，预览满意后点击「保存调整」。", -1)),
                  _createVNode(_component_v_btn, {
                    class: "mt-3",
                    color: "primary",
                    variant: "tonal",
                    "prepend-icon": "mdi-tune",
                    onClick: _cache[4] || (_cache[4] = ($event) => emit("switch"))
                  }, {
                    default: _withCtx(() => [..._cache[23] || (_cache[23] = [
                      _createTextVNode("打开详情页", -1)
                    ])]),
                    _: 1
                  })
                ]),
                _cache[26] || (_cache[26] = _createElementVNode("div", { class: "ap-setting-row" }, [
                  _createElementVNode("h3", null, "选择优先级"),
                  _createElementVNode("p", { class: "ap-muted" }, " 个人指定的形象优先；选择“跟随系统默认”的用户会使用系统默认 Pet。请在 MP 的智能助手配置中选择形象。 ")
                ], -1))
              ], 64)) : _createCommentVNode("", true),
              visitedPacks.value ? _withDirectives((_openBlock(), _createBlock(PackManager, {
                ref_key: "packManager",
                ref: packManager,
                key: props.pluginId,
                api: props.api,
                "plugin-id": props.pluginId,
                onChanged: refresh
              }, null, 8, ["api", "plugin-id"])), [
                [_vShow, activeMain.value === "packs"]
              ]) : _createCommentVNode("", true),
              visitedMarket.value ? _withDirectives((_openBlock(), _createBlock(MarketBrowser, {
                key: props.pluginId,
                api: props.api,
                "plugin-id": props.pluginId,
                onImported: marketImported
              }, null, 8, ["api", "plugin-id"])), [
                [_vShow, activeMain.value === "market"]
              ]) : _createCommentVNode("", true)
            ], 2)
          ]),
          _createElementVNode("footer", _hoisted_22, [
            changed.value ? (_openBlock(), _createElementBlock("span", _hoisted_23, [
              _createVNode(_component_v_icon, {
                icon: "mdi-circle",
                size: "7"
              }),
              _cache[27] || (_cache[27] = _createTextVNode("1 项未保存 · 启用助手形象", -1))
            ])) : (_openBlock(), _createElementBlock("span", _hoisted_24, _toDisplayString(activeMain.value === "packs" || activeMain.value === "market" ? "素材的导入与删除即时保存" : "修改配置后点击保存"), 1)),
            _createElementVNode("div", _hoisted_25, [
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: _cache[5] || (_cache[5] = ($event) => emit("close"))
              }, {
                default: _withCtx(() => [..._cache[28] || (_cache[28] = [
                  _createTextVNode("取消", -1)
                ])]),
                _: 1
              }),
              _createVNode(_component_v_btn, {
                color: "primary",
                variant: "flat",
                "prepend-icon": "mdi-content-save-outline",
                disabled: !changed.value || saving.value,
                loading: saving.value,
                onClick: save
              }, {
                default: _withCtx(() => [..._cache[29] || (_cache[29] = [
                  _createTextVNode("保存配置", -1)
                ])]),
                _: 1
              }, 8, ["disabled", "loading"])
            ])
          ])
        ])
      ]);
    };
  }
});

export { _sfc_main as _ };
