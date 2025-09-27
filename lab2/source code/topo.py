from mininet.topo import Topo

class MyTopo(Topo):
    def __init__(self):
        super(MyTopo, self).__init__()

        # 建立交換器 (OpenFlow switches)
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        s3 = self.addSwitch('s3')
        s4 = self.addSwitch('s4')
        s5 = self.addSwitch('s5')
        s6 = self.addSwitch('s6')
        s7 = self.addSwitch('s7')
        s8 = self.addSwitch('s8')

        # 建立主機 (Hosts)
        h1 = self.addHost('h1', ip='10.0.0.1/24')
        h2 = self.addHost('h2', ip='10.0.0.2/24')
        h3 = self.addHost('h3', ip='10.0.0.3/24')
        h4 = self.addHost('h4', ip='10.0.0.4/24')
        h5 = self.addHost('h5', ip='10.0.0.5/24')
        h6 = self.addHost('h6', ip='10.0.0.6/24')
        h7 = self.addHost('h7', ip='10.0.0.7/24')
        h8 = self.addHost('h8', ip='10.0.0.8/24')
        h9 = self.addHost('h9', ip='10.0.0.9/24')

        # 主機連結（Host port固定為0，Switch從1開始編）
        self.addLink(h1, s1, port1=0, port2=1)
        self.addLink(h2, s3, port1=0, port2=1)
        self.addLink(h3, s7, port1=0, port2=1)
        self.addLink(h4, s5, port1=0, port2=1)
        self.addLink(h5, s5, port1=0, port2=2)
        self.addLink(h6, s8, port1=0, port2=1)
        self.addLink(h7, s8, port1=0, port2=2)
        self.addLink(h8, s6, port1=0, port2=1)
        self.addLink(h9, s4, port1=0, port2=1)

        # Switch間的連結 (雙方Switch各有自己的port編號)
        self.addLink(s1, s2, port1=2, port2=1)
        self.addLink(s1, s3, port1=3, port2=2)
        self.addLink(s1, s6, port1=4, port2=2)

        self.addLink(s2, s3, port1=2, port2=3)
        self.addLink(s2, s4, port1=3, port2=2)
        self.addLink(s2, s5, port1=4, port2=3)
        self.addLink(s2, s7, port1=5, port2=2)

        self.addLink(s3, s4, port1=4, port2=3)

        self.addLink(s4, s5, port1=4, port2=4)
        self.addLink(s4, s8, port1=5, port2=3)

        self.addLink(s5, s7, port1=5, port2=3)
        self.addLink(s5, s8, port1=6, port2=4)

        self.addLink(s6, s7, port1=3, port2=4)

topos = { 'mytopo': MyTopo }
