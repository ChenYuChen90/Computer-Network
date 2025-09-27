from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.app.wsgi import WSGIApplication, ControllerBase, route
from webob import Response
import json
import heapq

REST_API_PREFIX = '/v1.0'

class DualPathController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super(DualPathController, self).__init__(req, link, data, **config)
        self.dualpath_app = data['dualpath_app']

    @route('dualpath', REST_API_PREFIX + '/dualpath/route', methods=['POST'])
    def set_route(self, req, **kwargs):
        try:
            data = req.json if req.body else {}
            src = data.get('src', None)
            dst = data.get('dst', None)

            if not src or not dst:
                return self._error_response('src or dst missing')

            host_data = self.dualpath_app.topology_data.get('hosts', {})
            if src not in host_data or dst not in host_data:
                return self._error_response('src or dst host not found in topology_data')

            src_ip = host_data[src]['ip']
            dst_ip = host_data[dst]['ip']
            src_dpid = host_data[src]['dpid']
            dst_dpid = host_data[dst]['dpid']

            # 計算第一條最短路徑
            path1 = self.dualpath_app.compute_shortest_path(src_dpid, dst_dpid)
            if not path1:
                return self._error_response('No path found between src and dst')

            # 提高第一條路徑的權重
            self.dualpath_app.increase_path_weight(path1, factor=1000)

            # 計算第二條路徑
            path2 = self.dualpath_app.compute_shortest_path(src_dpid, dst_dpid)

            # 還原權重
            self.dualpath_app.reset_weights()

            # 下發 flow entries 到 switch 上 (包含反向)
            if path1:
                # 正向
                self.dualpath_app.install_flow_for_path(src_ip, dst_ip, path1)
                # 反向（直接reverse路徑，並交換src/dst IP）
                reversed_path1 = path1[::-1]
                self.dualpath_app.install_flow_for_path(dst_ip, src_ip, reversed_path1)

            if path2:
                self.dualpath_app.install_flow_for_path(src_ip, dst_ip, path2)
                reversed_path2 = path2[::-1]
                self.dualpath_app.install_flow_for_path(dst_ip, src_ip, reversed_path2)

            result = {
                'status': 'success',
                'message': 'Found paths and installed flows',
                'src': src,
                'dst': dst,
                'src_ip': src_ip,
                'dst_ip': dst_ip,
                'path1': path1,
                'path2': path2 if path2 else 'No second path found or not disjoint enough'
            }
            return self._json_response(result)

        except Exception as e:
            return self._error_response(str(e))

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        return Response(status=status, content_type='application/json', text=body, charset='utf-8')

    def _error_response(self, message, status=400):
        data = {
            'status': 'error',
            'message': message
        }
        return self._json_response(data, status)

class DualPathRyuApp(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    _CONTEXTS = {
        'wsgi': WSGIApplication
    }

    def __init__(self, *args, **kwargs):
        super(DualPathRyuApp, self).__init__(*args, **kwargs)
        wsgi = kwargs['wsgi']
        wsgi.register(DualPathController, {'dualpath_app': self})

        self.datapaths = {}

        self.topology_data = {
            'graph': {
                1: {2:{'weight':1,'port':2}, 3:{'weight':1,'port':3}, 6:{'weight':1,'port':4}},
                2: {1:{'weight':1,'port':1}, 3:{'weight':1,'port':2}, 4:{'weight':1,'port':3}, 5:{'weight':1,'port':4}, 7:{'weight':1,'port':5}},
                3: {1:{'weight':1,'port':2}, 2:{'weight':1,'port':3}, 4:{'weight':1,'port':4}},
                4: {2:{'weight':1,'port':2}, 3:{'weight':1,'port':3}, 5:{'weight':1,'port':4}, 8:{'weight':1,'port':5}},
                5: {2:{'weight':1,'port':3}, 4:{'weight':1,'port':4}, 7:{'weight':1,'port':5}, 8:{'weight':1,'port':6}},
                6: {1:{'weight':1,'port':2}, 7:{'weight':1,'port':3}},
                7: {2:{'weight':1,'port':2}, 5:{'weight':1,'port':3}, 6:{'weight':1,'port':4}},
                8: {4:{'weight':1,'port':3}, 5:{'weight':1,'port':4}}
            },
            'hosts': {
                'h1': {'ip': '10.0.0.1', 'dpid': 1, 'port':1},
                'h2': {'ip': '10.0.0.2', 'dpid': 3, 'port':1},
                'h3': {'ip': '10.0.0.3', 'dpid': 7, 'port':1},
                'h4': {'ip': '10.0.0.4', 'dpid': 5, 'port':1},
                'h5': {'ip': '10.0.0.5', 'dpid': 5, 'port':2},
                'h6': {'ip': '10.0.0.6', 'dpid': 8, 'port':1},
                'h7': {'ip': '10.0.0.7', 'dpid': 8, 'port':2},
                'h8': {'ip': '10.0.0.8', 'dpid': 6, 'port':1},
                'h9': {'ip': '10.0.0.9', 'dpid': 4, 'port':1}
            }
        }

        self.original_weights = self.copy_weights()

    def copy_weights(self):
        original = {}
        for u in self.topology_data['graph']:
            original[u] = {}
            for v, info in self.topology_data['graph'][u].items():
                original[u][v] = info['weight']
        return original

    def reset_weights(self):
        # 將所有權重恢復
        for u in self.original_weights:
            for v in self.original_weights[u]:
                self.topology_data['graph'][u][v]['weight'] = self.original_weights[u][v]

    def compute_shortest_path(self, src, dst):
        graph = self.topology_data['graph']
        dist = {node: float('inf') for node in graph}
        dist[src] = 0
        prev = {node: None for node in graph}
        pq = [(0, src)]
        heapq.heapify(pq)

        while pq:
            current_dist, u = heapq.heappop(pq)
            if u == dst:
                break
            if current_dist > dist[u]:
                continue
            for v, info in graph[u].items():
                w = info['weight']
                new_dist = dist[u] + w
                if new_dist < dist[v]:
                    dist[v] = new_dist
                    prev[v] = u
                    heapq.heappush(pq, (new_dist, v))

        if dist[dst] == float('inf'):
            return None

        path = []
        node = dst
        while node is not None:
            path.append(node)
            node = prev[node]
        path.reverse()
        return path

    def increase_path_weight(self, path, factor=5):
        graph = self.topology_data['graph']
        for i in range(len(path)-1):
            u = path[i]
            v = path[i+1]
            # 雙向都增加
            graph[u][v]['weight'] *= factor
            graph[v][u]['weight'] *= factor

    def install_flow_for_path(self, src_ip, dst_ip, path):
        # 取得目標 host 的 dp與port
        hosts_info = self.topology_data['hosts']
        dst_dpid = None
        dst_port = None
        for h, info in hosts_info.items():
            if info['ip'] == dst_ip:
                dst_dpid = info['dpid']
                dst_port = info['port']
                break

        graph = self.topology_data['graph']

        for i in range(len(path)):
            dpid = path[i]
            if dpid not in self.datapaths:
                continue
            datapath = self.datapaths[dpid]
            parser = datapath.ofproto_parser
            ofproto = datapath.ofproto

            if i == len(path)-1:
                # 最後一個 switch 連接 host
                out_port = dst_port
            else:
                next_hop = path[i+1]
                out_port = graph[dpid][next_hop]['port']

            # 安裝 IPv4 Flow
            match_ip = parser.OFPMatch(
                eth_type=0x0800,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip
            )
            actions = [parser.OFPActionOutput(out_port)]
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
            mod_ip = parser.OFPFlowMod(
                datapath=datapath, 
                priority=1, 
                match=match_ip, 
                instructions=inst
            )
            datapath.send_msg(mod_ip)

            # 同時安裝 ARP Flow
            # 匹配目標 IP 為 dst_ip 的 ARP 封包
            match_arp = parser.OFPMatch(
                eth_type=0x0806,
                arp_tpa=dst_ip
            )
            mod_arp = parser.OFPFlowMod(
                datapath=datapath, 
                priority=1, 
                match=match_arp, 
                instructions=inst
            )
            datapath.send_msg(mod_arp)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        # 新增基本 rule，允許未匹配封包送 packet_in
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # 剛連接上來的 switch 預設下發一條表項將不匹配的封包送到controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=0,
                                match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        # 紀錄連上 controller 的 switch datapath
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                del self.datapaths[datapath.id]

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        # 若有封包抵達controller，之後可再依需求處理
        pass
