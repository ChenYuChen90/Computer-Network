from mininet.topo import Topo

class MyTopo(Topo):
    def __init__(self):
        Topo.__init__(self)
        
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        s3 = self.addSwitch('s3')

        host_a = self.addHost('A', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
        host_b = self.addHost('B', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
        host_c = self.addHost('C', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
        host_d = self.addHost('D', ip='10.0.0.4/24', mac='00:00:00:00:00:04')

        self.addLink(host_a, s3, port1=0, port2=1)
        self.addLink(host_b, s1, port1=0, port2=3)  # B 的接口 eth0 -> S1 的端口 1
        self.addLink(host_c, s2, port1=0, port2=3)  # C 的接口 eth0 -> S2 的端口 1
        self.addLink(host_d, s2, port1=0, port2=2)  # D 的接口 eth0 -> S2 的端口 2

        # 连接交换机之间的端口
        self.addLink(s1, s2, port1=2, port2=4)  # S1 的端口 2 -> S2 的端口 3
        self.addLink(s2, s3, port1=1, port2=2)  # S2 的端口 4 -> S3 的端口 2
        self.addLink(s3, s1, port1=3, port2=1)  # S3 的端口 3 -> S1 的端口 3

topos = { 'mytopo':  MyTopo }


