from __future__ import absolute_import

from Bio import SeqIO, Seq
from Bio.Alphabet import IUPAC
from Bio.SeqUtils import GC

from math import log, log10
import re

from .memoize import memoize
from . import xmlwriter

from .nucleotide import *

__all__ = ['Primer', 'PrimerPair', 'PrimerCondition', 'PCR', 'primers_write_html', 'primers_write_csv']


def annealing_score_n(x,y):
    if (x=='A' and y=='T') or (x=='T' and y=='A'):
        return 2
    elif (x=='G' and y=='C') or (x=='C' and y=='G'):
        return 4
    else:
        return 0

def annealing_score(p,q,end_annealing=False,getindex=False):
    sv = annealing_score_n
    p = str(p).upper()
    q = str(q).upper()
    w = p
    v = q[::-1]
    n = len(w)
    m = len(v)

    def ea(ss):
        ret = 0
        for n in ss:
            if n==0:
                return ret
            ret += n
        return ret
    def ea_l(ss):
        return ea(ss)
    def ea_r(ss):
        return ea(ss[::-1])
    def ea_lr(ss):
        return max(ea_l(ss),ea_r(ss))

    def max_(old, new):
        old_s,v = old
        new_s,vv = new
        if old_s<new_s:
            return new
        return old

    eav = (-1, None)
    av = (-1, None)
    if n<=m:
        assert m-n >= 0
        for k in xrange(-(n-1),m-1 +1):
            if k<=0:
                # 5'- w[0]....w[-k]....w[n-1] -3'
                #         3'- v[0].....v[n+k-1]....v[m-1] -5'
                ss = [sv(w[-k+i],v[i]) for i in xrange(n+k)]
                av = max_(av, (sum(ss),(k,ss)))
                eav = max_(eav,(ea_lr(ss),(k,ss)))
            elif k<=m-n:
                #         w[0]....w[n-1]
                # v[0]....v[k]....v[k+n-1].....v[m-1]
                ss = [sv(w[0+i],v[k+i]) for i in xrange(n)]
                av = max_(av, (sum(ss),(k,ss)))
                eav = max_(eav,(ea_r(ss),(k,ss)))
            else:
                #        w[0]...w[m-k-1]....w[n-1]
                # v[0]...v[k]...v[m-1]
                ss = [sv(w[i],v[k+i]) for i in xrange(m-k)]
                av = max_(av, (sum(ss),(k,ss)))
    else:
        assert m-n <= 0
        for k in xrange(-(n-1),m-1 +1):
            if k<=m-n:
                # w[0]....w[-k]....w[n-1]
                #         v[0].....v[n+k-1]....v[m-1]
                ss = [sv(w[-k+i],v[i]) for i in xrange(n+k)]
                av = max_(av, (sum(ss),(k,ss)))
                eav = max_(eav,(ea_lr(ss),(k,ss)))
            elif k<=0:
                # w[0]....w[k]....w[m-k-1].....w[n-1]
                #         v[0]....v[m-1]
                ss = [sv(w[k+i],v[0+i]) for i in xrange(m)]
                av = max_(av, (sum(ss),(k,ss)))
                eav = max_(eav,(ea_l(ss),(k,ss)))
            else:
                #        w[0]...w[m-k-1]....w[n-1]
                # v[0]...v[k]...v[m-1]
                ss = [sv(w[i],v[k+i]) for i in xrange(m-k)]
                av = max_(av, (sum(ss),(k,ss)))

    if not end_annealing:
        return av[0], av[1]
    else:
        return eav[0], eav[1]

class Annealing(object):
    def __init__(self, p, q, end_annealing=False):
        s, (i, ss) = annealing_score(p,q,end_annealing)
        self.p = p
        self.q = q
        self.score = s
        self.scores = ss
        self.index = i


    def get_bar(self):
        sv = annealing_score_n

        i = self.index
        p = self.p
        q = self.q
        lp = len(p)
        lq = len(q)
        spc = ' '*abs(i)
        ss = self.scores
        bar = ''.join(['|' if s>0 else ' ' for s in ss])

        if i>0:
            return [spc+"5'-%s-3'"%p, spc+"  <"+bar+">", "3'-%s-5'"%q[::-1] ]
        else:
            return ["5'-%s-3'"%p, spc+"  <"+bar+">", spc+"3'-%s-5'"%q[::-1] ]

    def write_html(self, w):
        w.push('div',style='annealing')
        w.push('p','pea=%s, index=%s'%(pea.score,self.index))
        w.push('pre')
        w.text('\n'.join(self.get_bar()))
        w.pop()
        w.pop()

NNT_DH = {
    'AA': 9.1,
    'TT': 9.1,
    'AT': 8.6,
    'TA': 6.0,
    'CA': 5.8,
    'TG': 5.8,
    'GT': 6.5,
    'AC': 6.5,
    'CT': 7.8,
    'AG': 7.8,
    'GA': 5.6,
    'TC': 5.6,
    'CG': 11.9,
    'GC': 11.1,
    'GG': 11.0,
    'CC': 11.0,
}
NNT_DG = {
    'AA': 1.55,
    'TT': 1.55,
    'AT': 1.25,
    'TA': 0.85,
    'CA': 1.15,
    'TG': 1.15,
    'GT': 1.40,
    'AC': 1.40,
    'CT': 1.45,
    'AG': 1.45,
    'GA': 1.15,
    'TC': 1.15,
    'CG': 3.05,
    'GC': 2.70,
    'GG': 2.3,
    'CC': 2.3,
}

DEFAULT_C_NA = 33.*10**-3
DEFAULT_C_MG = (2+4.5)*10**-3
DEFAULT_C_PRIMER = 0.5*10**-6

def melting_temperature_unambiguous(seq, c_na=DEFAULT_C_NA, c_mg=DEFAULT_C_MG, c_primer=DEFAULT_C_PRIMER):
    '''
    c_na, c_mg: final concentration in molar of Na and Mg in PCR reaction mix
                these are used for calculation of salt concentration
    c_primer:   final concentration in molar of each primer in PCR reaction mix
    unmethyl:   if 'unmethyl' is true, all CpGs of template are assumed to be unmethyled
                then unmethyl version of primer are used for calculation
    '''

    # c_salt: salt concentration in molar
    c_salt = c_na + 4*(c_mg**0.5)

    l = len(seq)
    t0 = 298.2
    r = 1.987
    d_h_e = 5.
    d_h_p = -1000. * ( 2*d_h_e + sum([NNT_DH[seq[i:i+2]] for i in range(l-1)]) )
    d_g_e = 1.
    d_g_i = -2.2
    d_g_p = -1000. * ( 2*d_g_e + d_g_i + sum([NNT_DG[seq[i:i+2]] for i in range(l-1)]) )
    t_p = t0*d_h_p / (d_h_p-d_g_p + r*t0*log(c_primer) ) + 16.6*log10(c_salt / (1.+0.7*c_salt)) - 269.3
    return t_p

def melting_temperature_unmethyl(seq, c_na=DEFAULT_C_NA, c_mg=DEFAULT_C_MG, c_primer=DEFAULT_C_PRIMER, unmethyl=True):
    seq = str(seq).upper()
    if unmethyl:
        seq = seq.replace('R','A').replace('Y','T')
    else:
        seq = seq.replace('R','G').replace('Y','C')

    return melting_temperature_unambiguous(seq, c_na, c_mg, c_primer)


class Primer(object):
    def __init__(self, name, seq):
        self.name = name
        self.seq = seq
    def __repr__(self):
        return "Primer(%s: %s)"%(self.name,self.seq)
    def __len__(self):
        return len(self.seq)
    def __str__(self):
        return str(self.seq)

    def reverse(self):
        return self.seq[::-1]

    @property
    @memoize
    def gc_ratio(self):
        return GC(self.seq)

    def melting_temperature(self, c_na=DEFAULT_C_NA, c_mg=DEFAULT_C_MG, c_primer=DEFAULT_C_PRIMER, unmethyl=True):
        return melting_temperature_unmethyl(self.seq, c_na, c_mg, c_primer, unmethyl)

    @property
    @memoize
    def self_annealing(self):
        return Annealing(self.seq, self.seq)
    @property
    @memoize
    def self_end_annealing(self):
        return Annealing(self.seq, self.seq, True)

    sa = self_annealing
    sea = self_end_annealing

    def search(self, template):
        def _gen_re_seq(seq):
            table = {
                'A': 'A',
                'T': 'T',
                'G': 'G',
                'C': 'C',
                'R': '[GA]',
                'Y': '[TC]',
                'M': '[AC]',
                'K': '[GT]',
                'S': '[GC]',
                'W': '[AT]',
                'H': '[ACT]',
                'B': '[GTC]',
                'V': '[GCA]',
                'D': '[GAT]',
                'N': '[GATC]',
                }
            return ''.join([table[s] for s in str(seq).upper()])

        primer = self.seq
        cprimer = self.seq.reverse_complement()
        reg = re.compile('(%s)|(%s)'%(_gen_re_seq(primer),_gen_re_seq(cprimer)))

        template = str(template).upper()
        pp = []
        pc = []
        start = 0
        while True:
            m = reg.search(template, start)
            if not m:
                break
            start = m.start()+1
            if m.group(1):
                pp.append(m.start())
            if m.group(2):
                pc.append(m.start())
        return pp,pc

    def debugprint(self):
        print "%s: %s, len=%2d, Tm=%.2f, oTm=%.2f, MarmurTm: %s, GC=%.2f, sa=%2d, sea=%2d" % self.get_table_row()
        print 'sa=%s, index=%s'%(self.sa.score, self.sa.index)
        print '\n'.join(self.sa.get_bar())
        print 'sea=%s, index=%s'%(self.sea.score, self.sea.index)
        print '\n'.join(self.sea.get_bar())


    @classmethod
    def get_table_head(cls):
        return ['name', 'sequence', 'length[bp]', 'Tm[C]', 'oTm[C]', 'old Tm[C]','GC[%]', 'sa.', 'sea.']

    def get_table_row(self):
        return [str(v) for v in [self.name,
                                 "5'-%s-3'"%self.seq,
                                 len(self),
                                 '%.2f'%self.melting_temperature(),
                                 '%.2f'%self.melting_temperature(unmethyl=False),
                                 tm_gc(self.seq),
                                 '%.2f'%self.gc_ratio,
                                 self.sa.score,
                                 self.sea.score]]
    @property
    @memoize
    def score(self):
        pc = PrimerCondition()

        return pc.primer_length.score(len(self)) \
              + pc.gc.score(self.gc_ratio) \
              + pc.tm.score(self.melting_temperature()) \
              + pc.sa.score(self.sa.score) \
              + pc.sea.score(self.sea.score)

'''
class PrimerAnneal(object):
    def __init__(self, template, primer, location, strand, match):
        self.template = template
        self.primer = primer
        self.location = location
        self.strand = strand
        self.match = match
        
class PrimerAnneals(object):
    def __init__(self, template, primer, partial=-1):
        def _gen_re_seq(seq):
            table = {
                'A': 'A',
                'T': 'T',
                'G': 'G',
                'C': 'C',
                'R': '[GA]',
                'Y': '[TC]',
                'M': '[AC]',
                'K': '[GT]',
                'S': '[GC]',
                'W': '[AT]',
                'H': '[ACT]',
                'B': '[GTC]',
                'V': '[GCA]',
                'D': '[GAT]',
                'N': '[GATC]',
                }
            return ''.join([table[s] for s in str(seq).upper()])

        seqs = str(template).upper()

        cprimer = primer.reverse_complement()
        if str(primer).upper()==str(cprimer).upper():
            p = []
            reg = re.compile('(%s)'%(_gen_re_seq(primer)))

            start = 0
            while True:
                m = reg.search(seqs, start)
                if not m:
                    break
                start = m.start()+1
                if m.group(1):
                    pp.append(m.start())
            self.fwrv_match = p
            return
        else:
             reg = re.compile('(%s)|(%s)'%(_gen_re_seq(primer),_gen_re_seq(cprimer)))

        seqs = str(template).upper()
        pp = []
        pc = []
        start = 0
        while True:
            m = reg.search(seqs, start)
            if not m:
                break
            start = m.start()+1
            if m.group(1):
                pp.append(m.start())
            if m.group(2):
                pc.append(m.start())
        return pp,pc
'''    


class PCRProduct(object):
    def __init__(self, template, start, end, primer_fw, primer_rv):
        self.template = template
        self.seq = template[start:end]
        self.start = start
        self.start_i = start+len(primer_fw)
        self.end = end
        self.end_i = end-len(primer_rv)
        self.fw = primer_fw
        self.rv = primer_rv
        self.head = template[self.start:self.start_i]
        self.middle = template[self.start_i:self.end_i]
        self.tail = template[self.end_i:self.end]

    def __repr__(self):
        return "PCRProduct(%s -> %s: %s)"%(self.fw.name, self.rv.name, self.seq)

    def __len__(self):
        return len(self.seq)

    def __str__(self):
        return str(self.seq)

    def detectable_cpg(self):
        return len(self.cpg_sites())

    def cpg_sites(self):
        s = self.start_i-1
        e = self.end_i+1
        return [i+s for i in cpg_sites(self.template[s:e])]

    def write_html(self, w):
        b = xmlwriter.builder(w)
        seqstr = self.seq

        with b.div:
            cpg = count_cpg(self.seq)
            b.text('forward primer=%s, reverse primer=%s '%(self.fw.name, self.rv.name))
            b.text('length=%d, CpG=%d, detectable CpG=%d'%(len(self), cpg, self.detectable_cpg()))
            b.br

            s = self.start
            cm = ColorMap()
            for i in range(0, self.start_i-s):
                cm.add_color(i, 0, 200, 0)
            for i in range(self.end_i-s, self.end-s):
                cm.add_color(i, 0, 0, 200)
            for i in self.cpg_sites():
                cm.add_color(i-s, 255, 0, 0)
                cm.add_color(i+1-s, 255, 0, 0)

            pprint_sequence_html(w, self.seq, cm.get_color)

            with b.textarea(cols='10', rows='1', cls='copybox'):
                w.write(str(self.seq))

class Condition(object):
    def __init__(self, weight, optimal, minimum, maximum):
        self.optimal = optimal
        self.weight = weight
        self.minimum = minimum
        self.maximum = maximum
    def score(self, value):
        return self.weight * abs(value-self.optimal)
    def bound(self, value):
        return self.minimum <= value <= self.maximum

class PrimerCondition(object):
    def __init__(self):
        self.primer_length = Condition(0.5, 23., 10, 30)
        self.gc            = Condition(1.0, 50., 30, 70)
        self.gc_bsp        = Condition(1.0, 30., 0, 60)
        self.tm            = Condition(1.0, 60., 45, 70)
        self.sa            = Condition(0.1, 0., 0, 25)
        self.sea           = Condition(0.2, 0., 0, 15)
        self.pa            = Condition(0.1, 0., 0, 25)
        self.pea           = Condition(0.2, 0., 0, 15)

class PrimerPair(object):
    def __init__(self, fw, rv):
        self.fw = fw
        self.rv = rv

    @property
    @memoize
    def pair_annealing(self):
        return Annealing(self.fw.seq, self.rv.seq)
    @property
    @memoize
    def pair_end_annealing(self=False):
        return Annealing(self.fw.seq, self.rv.seq, True)

    pa = pair_annealing
    pea = pair_end_annealing

    @property
    @memoize
    def score(self):
        pc = PrimerCondition()

        return self.fw.score + self.rv.score + pc.pa.score(self.pa.score) + pc.pea.score(self.pea.score)

    def debugprint(self):
        print 'score=', self.score()
        for r in [self.fw, self.rv]:
            r.debugprint()
        pa = self.pair_annealing()
        print 'pa=%s, index=%s'%(pa.score,pa.index)
        print '\n'.join(pa.get_bar())
        pea = self.pair_end_annealing()
        print 'pea=%s, index=%s'%(pea.score,pea.index)
        print '\n'.join(pea.get_bar())


    def write_html(self, w):
        b = xmlwriter.builder(w)
        # primer table
        with b.div(cls='primerpair'):
            with b.table(cls='primerpairtable', border=1):
                with b.tr:
                    for p in (Primer.get_table_head() + ['pa.', 'pea.', 'pair score']):
                        b.th(p)

                with b.tr:
                    for v in self.fw.get_table_row():
                        b.td(str(v))
                    for v in [self.pa.score, self.pea.score, '%.2f'%self.score]:
                        b.td(str(v),rowspan='2')
                with b.tr:
                    for v in self.rv.get_table_row():
                        b.td(str(v))

            b.p('Tm melting temperature(SantaLucia), oTm melting temperature for bisulfite methyl-template, sa. self annealing, sea. self end annealing, pa. pair annealing, pea. pair end annealing', style='font-size:x-small')

def primers_write_csv(primers):
    ret = ""
    ret += ", ".join(Primer.get_table_head())
    ret += "\n"

    for r in primers:
        ret += (", ".join([str(v) for v in r.get_table_row()]) + "\n")

    return ret+"\n"

def primers_write_html(w, primers):
    b = xmlwriter.builder(w)
    # primer table
    with b.div(cls='primerpair'):
        with b.table(cls='primerpairtable', border=1):
            with b.tr:
                for p in Primer.get_table_head():
                    b.th(p)

            for r in primers:
                with b.tr:
                    for v in r.get_table_row():
                        b.td(str(v))

        b.p('Tm melting temperature(SantaLucia), oTm melting temperature for bisulfite methyl-template, sa. self annealing, sea. self end annealing, pa. pair annealing, pea. pair end annealing', style='font-size:x-small')


class PCR(object):
    def __init__(self, name, template, primer_fw, primer_rv):
        self.name = name
        self.template = template
        self.primers = PrimerPair(primer_fw,primer_rv)

    @property
    def fw(self):
        return self.primers.fw
    @property
    def rv(self):
        return self.primers.rv

    @property
    @memoize
    def pair_annealing(self):
        return self.primers.pair_annealing

    @property
    @memoize
    def pair_end_annealing(self):
        return self.primers.pair_end_annealing

    @property
    @memoize
    def primer_score(self):
        return self.primers.score

    @property
    @memoize
    def products(self):
        return list(self._search(self.template))

    @property
    @memoize
    def bs_met_products(self):
        return list(self._search(bisulfite(self.template, True)))

    @property
    @memoize
    def bs_unmet_products(self):
        return list(self._search(bisulfite(self.template, False)))

    def _search(self, template):
        def d(fw, rv, i, j):
            return PCRProduct(template, i, j+len(rv), fw, rv)
        fpp,fpc = self.fw.search(template)
        rpp,rpc = self.rv.search(template)
        for i in fpp:
            for j in fpc:
                if i<=j:
                    yield d(self.fw, self.fw, i, j)
            for j in rpc:
                if i<=j:
                    yield d(self.fw, self.rv, i, j)
        for i in rpp:
            for j in fpc:
                if i<=j:
                    yield d(self.rv, self.fw, i, j)
            for j in rpc:
                if i<=j:
                    yield d(self.rv, self.rv, i, j)

    @property
    @memoize
    def bisulfite_products(self):
        """
        return list of the tuple: (met_product, unmet_product, genome_product)
        products in the same position are in the same tuple.
        if not all products are exist, the other values are None.
        """
        ret = defaultdict(lambda: [None,None,None])
        
        for p in self.bs_met_products:
            ret[(p.start,p.end,p.fw,p.rv)][0] = p

        for p in self.bs_unmet_products:
            ret[(p.start,p.end,p.fw,p.rv)][1] = p

        for p in self.products:
            ret[(p.start,p.end,p.fw,p.rv)][2] = p

        return list(ret.values())

    def debugprint(self):
        print '%s: score=%.2f'%(self.name, self.primer_score())
        self.primers.debugprint()
        for c in self.products:
            print 'product: len=%d, detectable CpG=%d'%(len(c),c.detectable_cpg())
            print c.seq

    def write_html(self, w):
        b = xmlwriter.builder(w)
        with b.div:
            b.h2(self.name)

            self.primers.write_html(w)
            #self.pair_annealing().write_html(w)
            #self.pair_end_annealing().write_html(w)
            for c in self.products:
                c.write_html(w)

