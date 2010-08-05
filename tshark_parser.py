#!/usr/bin/env python2.6

import sys
from xml.dom.minidom import parseString
from optparse import OptionParser
from hashlib import sha1
from os import listdir
from os.path import isfile


DATA_TYPES = ['TEXT', 'HEX', 'FILE']

VERSION = '0.1b'

PROTOS = { }

# incomplete data container - [ModuleStorage]
idc = []
# complete data container - [DataStorage]
cdc = []
# key: ModuleStorage.id, value: idc index to key
hashTable = {}

histData = []

class DataStorage:
    '''Simple data storage'''
    def __init__(self, src='', dst='', dtype=0, desc='', proto='', value='', verified=False, notes=''):
        self.src      = src
        self.dst      = dst
        self.desc     = desc
        self.proto    = proto
        self.dtype    = dtype
        self.value    = value
        self.verified = verified
        self.notes    = notes
        # TODO date
        self.updateHash()
        self.updateId()

    def updateHash(self):
        self.hash = sha1("%s%s%d%s" % (self.src, self.dst, self.dtype, self.proto)).hexdigest()

    def updateId(self):
        self.id = sha1("%s%s%d%s%s" % (self.src, self.dst, self.dtype, self.proto, str(self.value))).hexdigest()
        # self.id = sha1(''.join([x.__str__() for x in filter(lambda x: not x.startswith('__'), self) if not callable(x)])).hexdigest()

    def __unicode__(self):
        return "Src: %s, Dst: %s\n %s\n id: %s\n notes: %s" % (self.src, self.dst, unicode(self.value), self.id, self.notes)

    def verify(self):
        if self.verified:
            return
        self.verified = True
        self.value.relevance += 10


class PacketParser:
    def __init__(self, packet_str):
        self.dom = parseString(packet_str).firstChild
        self.protos = []
        self.src = {}
        self.src_str = ''
        self.dst = {}
        self.dst_str = ''
        self.time = ''
        for x in self.dom.childNodes:
            self.protos.append(x.attributes['name'].value)
            if x.attributes['name'].value == 'ip':
                for ia in x.childNodes:
                    if ia.attributes['name'].value == 'ip.src':
                        self.src['ip'] = ia.attributes['show'].value
                        self.src_str += self.src['ip']
                    elif ia.attributes['name'].value == 'ip.dst':
                        self.dst['ip'] = ia.attributes['show'].value
                        self.dst_str += self.dst['ip']
                    elif ia.attributes['name'].value == 'ip.src_host':
                        self.src['host'] = ia.attributes['show'].value
                        self.src_str += '('+self.src['host']+')'
                    elif ia.attributes['name'].value == 'ip.dst_host':
                        self.dst['host'] = ia.attributes['show'].value
                        self.dst_str += '('+self.dst['host']+')'
            elif x.attributes['name'].value == 'tcp':
                for pa in x.childNodes:
                    if pa.attributes['name'].value == 'tcp.srcport':
                        self.src['port'] = int(pa.attributes['show'].value)
                    elif pa.attributes['name'].value == 'tcp.dstport':
                        self.dst['port'] = int(pa.attributes['show'].value)
            elif x.attributes['name'].value == 'geninfo':
                for ga in x.childNodes:
                    if ga.attributes['name'].value == 'timestamp':
                        self.time = ga.attributes['show'].value


    def decode(self):
        c = 0
        for (i, proto) in enumerate(self.dom.childNodes):
            p = proto.attributes['name'].value
            if not sys.modules.has_key("modules.mod_%s" % p):
                continue
            r = []
            r = globals()['mod_%s' % p].parse(self.dom.childNodes[i:])
            for d in r:
                ds = DataStorage(src=self.src['ip'], dst=self.dst['ip'], proto=p, value=d, notes='%s -> %s @ %s' % (self.src_str, self.dst_str, self.time))
                if d.verification:
                    for p in reversed(cdc):
                        if p.hash == ds.hash:
                            print '[!] Verification found for %s' % unicode(p)
                            # TODO check verification

                            break
                    continue
                if d.complete:
                    if ds.id in histData:
                        continue
                    cdc.append(ds)
                    histData.append(ds.id)
                    c += 1
                else:
                    if hashTable.has_key(ds.hash):
                        index = hashTable[ds.hash]
                        if ds.value.value.keys() != idc[index].value.keys():
                            ds.value.value.update(idc[index].value)
                            ds.value.complete = True
                            ds.value.order()
                            ds.updateId()
                            idc.pop(index)
                            hashTable.pop(ds.hash)
                            if ds.id in histData:
                                continue
                            histData.append(ds.id)
                            cdc.append(ds)
                            c += 1
                        else:
                            print 'duplicated item dropped'
                    else:
                        hashTable[ds.hash] = len(idc)
                        idc.append(d)
        return c


if __name__ == '__main__':
    usage = "usage: %prog [options]"
    parser = OptionParser(usage=usage, version=("%%prog %s" % VERSION))
    parser.add_option("-f", "--filter", action='store_true', dest='filter')
    (options, args) = parser.parse_args()
    FILTER_EXP = []
    # (short|long) proto description
    # TODO read module dir name from command line parameter
    for f in listdir('modules/'):
        if f.startswith('mod_') and f.endswith('.py') and isfile('modules/%s' % f):
            modname = f[:-3]
            try:
                exec('from modules import %s' % modname)
            except ImportError, e:
                if not options.filter:
                    print "[!] Import Error: %s" % e
            else:
                FILTER_EXP.append('('+globals()[modname].FILTER_EXPRESSION+')')
                PROTOS.update(globals()[modname].PROTO_NAME)
                if not options.filter:
                    print "[!] %s module loaded" % modname[4:]
    if not len(PROTOS):
        print "[!] 0 module found. exitting.."
        sys.exit(1)
    if options.filter:
        filter_str = ' or '.join(FILTER_EXP)
        print filter_str,
        sys.exit(0)
    xml_version = sys.stdin.readline()
    pdml_version = sys.stdin.readline()
    line = sys.stdin.readline()
    packet = []
    while(line):
        if line.strip() != '</pdml>' and line != pdml_version and line != xml_version:
            packet.append(line.strip())
            if line.strip() == '</packet>':
                try:
                    p = PacketParser(''.join(packet))
                except NameError, e:
                    print e
                else:
                    packets = p.decode()
                    if packets > 0:
                        # print "%s:%d -> %s:%d (%s) - %s" % (p.src['ip'], p.src['port'], p.dst['ip'], p.dst['port'], p.dst['host'], p.time)
                        # TODO !! 
                        print ('-'*40+'\n').join(map(unicode, cdc[-packets:]))
                        print '-'*88
                packet = []

        line = sys.stdin.readline()

    print '\nIncomplete packets:'
    print '\n'.join(map(unicode, idc))
    print '\n'.join(map(unicode, cdc))

