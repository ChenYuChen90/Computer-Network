from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet, ipv4, arp, tcp, udp

class SDNLabController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SDNLabController, self).__init__(*args, **kwargs)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

        # Allow ARP packets to be forwarded, but prevent broadcast storms between S1 and S2
        self.allow_arp_flood_with_restriction(datapath, parser, ofproto)

        # Allow A, B, C to communicate freely (OpenFlow rules for S1, S2, S3)
        self.allow_abc_communication(datapath, parser, ofproto)

        # Allow D to access A and B on ports 22 (SSH) and 80 (HTTP)
        self.allow_d_to_ab_ports(datapath, parser, ofproto)

        # Allow A and B to respond to D (for SYN-ACK)
        self.allow_ab_to_d_response(datapath, parser, ofproto)

        # Deny communication between D and C
        self.deny_d_to_c(datapath, parser, ofproto)

        # Deny all other communication from D to A and B
        self.deny_d_to_ab_other_ports(datapath, parser, ofproto)

        # Deny direct communication between S1 and S2 to avoid broadcast storm
        self.deny_s1_s2_link(datapath, parser, ofproto, priority=200)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id, priority=priority,
                                    match=match, instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst)
        datapath.send_msg(mod)

    def allow_arp_flood_with_restriction(self, datapath, parser, ofproto):
        # Allow ARP packets to be forwarded using FLOOD, but prevent ARP flood between S1 and S2 to avoid broadcast storm
        if datapath.id == 1:  # S1
            match = parser.OFPMatch(eth_type=0x0806, in_port=2)  # Block ARP flood on port 2 connecting to S2
            actions = []  # No actions imply dropping the packet
            self.add_flow(datapath, 100, match, actions)
        elif datapath.id == 2:  # S2
            match = parser.OFPMatch(eth_type=0x0806, in_port=4)  # Block ARP flood on port 4 connecting to S1
            actions = []
            self.add_flow(datapath, 100, match, actions)
        # Allow other ARP packets to be forwarded using FLOOD
        match = parser.OFPMatch(eth_type=0x0806)
        actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
        self.add_flow(datapath, 1, match, actions)

    def allow_abc_communication(self, datapath, parser, ofproto):
        # Allow A, B, C to communicate with each other freely
        # Assume IPs are in the 10.0.0.x/24 range, add appropriate rules
        ips = ['10.0.0.1', '10.0.0.2', '10.0.0.3']
        for ip_src in ips:
            for ip_dst in ips:
                if ip_src != ip_dst:
                    match = parser.OFPMatch(eth_type=0x0800, ipv4_src=ip_src, ipv4_dst=ip_dst)
                    actions = [parser.OFPActionOutput(ofproto.OFPP_NORMAL)]
                    self.add_flow(datapath, 2, match, actions)

    def allow_d_to_ab_ports(self, datapath, parser, ofproto):
        # Allow D (10.0.0.4) to access A (10.0.0.1) and B (10.0.0.2) on ports 22 and 80
        allowed_ips = ['10.0.0.1', '10.0.0.2']
        for ip_dst in allowed_ips:
            for port in [22, 80]:
                match = parser.OFPMatch(eth_type=0x0800, ipv4_src='10.0.0.4', ipv4_dst=ip_dst, ip_proto=6, tcp_dst=port)
                actions = [parser.OFPActionOutput(ofproto.OFPP_NORMAL)]
                self.add_flow(datapath, 20, match, actions)  # Increase priority to ensure this rule is matched

    def allow_ab_to_d_response(self, datapath, parser, ofproto):
        # Allow A and B to respond to D (e.g., TCP SYN-ACK packets)
        allowed_ips = ['10.0.0.1', '10.0.0.2']
        for ip_src in allowed_ips:
            match = parser.OFPMatch(eth_type=0x0800, ipv4_src=ip_src, ipv4_dst='10.0.0.4', ip_proto=6)
            actions = [parser.OFPActionOutput(ofproto.OFPP_NORMAL)]
            self.add_flow(datapath, 18, match, actions)  # Slightly lower priority than allow_d_to_ab_ports

    def deny_d_to_ab_other_ports(self, datapath, parser, ofproto):
        # Deny D (10.0.0.4) from accessing any other ports on A (10.0.0.1) and B (10.0.0.2)
        allowed_ips = ['10.0.0.1', '10.0.0.2']
        for ip_dst in allowed_ips:
            match = parser.OFPMatch(eth_type=0x0800, ipv4_src='10.0.0.4', ipv4_dst=ip_dst, ip_proto=6)
            self.add_flow(datapath, 15, match, [])  # Add a drop rule with lower priority than the allowed ports

    def deny_d_to_c(self, datapath, parser, ofproto):
        # Deny D (10.0.0.4) from communicating with C (10.0.0.3)
        match = parser.OFPMatch(eth_type=0x0800, ipv4_src='10.0.0.4', ipv4_dst='10.0.0.3')
        self.add_flow(datapath, 4, match, [])

        match = parser.OFPMatch(eth_type=0x0800, ipv4_src='10.0.0.3', ipv4_dst='10.0.0.4')
        self.add_flow(datapath, 4, match, [])

    def deny_s1_s2_link(self, datapath, parser, ofproto, priority=200):
        # Deny direct communication between S1 and S2 to avoid broadcast storm
        # Specifically blocking the correct ports connecting S1 and S2
        # Assuming S1 connects to S2 through port 2 and S2 connects to S1 through port 4
        if datapath.id == 1:  # S1
            match = parser.OFPMatch(eth_type=0x0800, in_port=2)  # Only block port 2 on S1 that connects to S2
            actions = []  # No actions imply dropping the packet
            self.add_flow(datapath, priority, match, actions)
        elif datapath.id == 2:  # S2
            match = parser.OFPMatch(eth_type=0x0800, in_port=4)  # Only block port 4 on S2 that connects to S1
            actions = []
            self.add_flow(datapath, priority, match, actions)
