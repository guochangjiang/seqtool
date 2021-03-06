from Bio import Seq
from Bio.Alphabet import IUPAC


from ..util import xmlwriter

seqfilter = str.maketrans({' ':None, '-':None})

def seqf(s):
    """
    >>> seqf("ATGC-atgc ATGC")
    'ATGCATGCATGC'
    """
    return str(s).upper().translate(seqfilter)

def to_ambiguous_seq(st):
    return Seq.Seq(st,IUPAC.ambiguous_dna)
def to_unambiguous_seq(st):
    return Seq.Seq(st,IUPAC.unambiguous_dna)

def is_sequence_like(s):
    """
    >>> is_sequence_like("7HOGEHOGEHOGE-")
    False
    >>> is_sequence_like("ATG-C-NYR")
    True
    """
    return all(n in IUPAC.ambiguous_dna.letters for n in seqf(s))

def to_seq(s):
    if isinstance(s, Seq.Seq):
        return s

    t = seqf(s)
    if all(n in IUPAC.unambiguous_dna.letters for n in t):
        return Seq.Seq(t,IUPAC.unambiguous_dna)
    elif all(n in IUPAC.ambiguous_dna.letters for n in t):
        return Seq.Seq(t,IUPAC.ambiguous_dna)
    else:
        raise ValueError("invalid DNA sequence, base must be one of %s: %s"%(IUPAC.ambiguous_dna.letters,s))

def base_color(n):
    return {'A':'#00FF00',
            'T':'#FF0000',
            'G':'#000000',
            'C':'#0000FF'}[n.upper()]

def tm_gc(seq):
    """
    >>> tm_gc(to_seq("ATGC"))
    '4x2+2x2=12'
    """
    gc = seq.count('G')+seq.count('C')
    at = seq.count('A')+seq.count('T')
    return '4x%s+2x%s=%s'%(gc,at,4*gc+2*at)

def repeat_no(seq, i):
    """
    >>> repeat_no(to_seq('ATGCCCATGC'), 4)
    3
    >>> repeat_no(to_seq('ATGCCCATGC'), 0)
    1
    >>> repeat_no(to_seq('ATGCCCATGC'), 9)
    1
    """
    v = seq[i]
    tail = 0
    for t in seq[i+1:]:
        if t!=v:
            break
        tail += 1
    head = 0
    for t in seq[:i][::-1]:
        if t!=v:
            break
        head += 1
    return tail+head+1
    
def is_repeat(seq,i,repeatno=8):
    r = repeat_no(seq, i)
    return r >= repeatno

class PPrintSequence(object):
    def __init__(self, seq):
        self.seq = seq
        self.length = len(seq)
        self.colors = [(0,0,0) for x in range(self.length)]
        self.underbar = [False for x in range(self.length)]

    def add_color(self, i, red, green, blue):
        r,g,b = self.colors[i]
        self.colors[i] = (r+red, g+green, b+blue)

    def add_underbar(self, i):
        self.underbar[i] = True

    def get_color(self, i):
        return '#%02x%02x%02x'%self.colors[i]

    def get_underbar(self, i):
        return self.underbar[i]

    def get_style(self, i):
        color = self.get_color(i)
        underbar = self.get_underbar(i)
        if underbar:
            return "color:%s; text-decoration:underline;"%color
        else:
            return "color:%s;"%color

    def write_html(self, w):
        b = xmlwriter.builder(w)
        seqstr = str(self.seq)
        length = len(self.seq)

        with b.pre:
            for i in range(0, length, 100):
                w.write('<span style="black">%4d: </span>'%i)
                oldstyle = ""
                inspan = False
                for ii in range(i, min(i+100, length), 10):
                    for iii in range(ii, min(ii+10, length), 1):
                        style = self.get_style(iii)

                        if oldstyle!=style:
                            if inspan:
                                w.write('</span>')
                            w.write('<span style="%s">'%style)

                            inspan = True
                            oldstyle = style
                        w.write(seqstr[iii])
                    if inspan:
                        w.write('</span>')
                        inspan = False
                        oldstyle = None

                    w.write(' ')

                w.write('\n')

def no_stop_in_frame(seq):
    s = seq
    stopped = all('*' in s[i:].translate() for i in range(3))
    s = seq.reverse_complement()
    stopped = stopped and all('*' in s[i:].translate() for i in range(3))
    return not stopped

def reverse(seq):
    """
    >>> reverse(to_seq("ATGC"))
    'CGTA'
    """
    return str(seq)[::-1]

def complement(seq):
    """
    >>> complement(to_seq("ATGC"))
    Seq('TACG', IUPACUnambiguousDNA())
    """
    return seq.complement()


def fasta_file(name, seq, width=70):
    ret = '>{}\n'.format(name)

    for i in range(0, len(seq), width):
        ret += str(seq[i:i+width])
        ret += '\n'
        
    return ret
    
