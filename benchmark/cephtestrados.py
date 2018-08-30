import subprocess
import common
import settings
import monitoring
import os
import threading
import logging

logger = logging.getLogger('cbt')

from cluster.ceph import Ceph
from benchmark import Benchmark

class CephTestRados(Benchmark):

    def __init__(self):
        super(CephTestRados, self).__init__()

    def load_config(self, cluster, config):
        super(CephTestRados, self).load_config(cluster, config)

        self.tmp_conf = self.cluster.tmp_conf

        self.bools = {}
        if config.get('ec_pool', False):  self.bools['ec_pool'] = True
        if config.get('write_fadvise_dontneed', False): self.bools['write_fadvise_dontneed'] = True
        if config.get('pool_snaps', False): self.bools['pool_snaps'] = True
        if config.get('write_append_excl', True): self.bools['write_append_excl'] = True

        self.variables = {}
        self.variables['object_size'] = int(config.get('object_size', 4000000))
        self.variables['max_ops'] = str(config.get('ops', 10000))
        self.variables['objects'] = str(config.get('objects', 500))
        self.variables['max_in_flight'] = str(config.get('max_in_flight', 16))
        self.variables['size'] = int(config.get('object_size', 4000000))
        self.variables['min_stride_size'] = str(config.get('min_stride_size', self.variables['object_size'] / 10))
        self.variables['max_stride_size'] = str(config.get('max_stride_size', self.variables['object_size'] / 5))
        self.variables['max_seconds'] = str(config.get('max_seconds', 0))


        self.weights = {'read': 100, 'write':100, 'delete':10}
        for weight in ['snap_create', 'snap_remove', 'rollback', 'setattr', 'rmattr', 'watch', 'copy_from', 'hit_set_list', 'is_dirty', 'cache_flush', 'cache_try_flush', 'cache_evict' 'append', 'write', 'read', 'delete']:
            self.addweight(weight)
        if 'write_append_excl' in self.bools and 'append' in self.weights:
            self.weights['append'] = self.weights['write'] / 2
            self.weights['append_excl'] = self.weights['write']

        if 'write_append_excl' in self.bools and 'write' in self.weights:
            self.weights['write'] = self.weights['write'] / 2
            self.weights['write_excl'] = self.weights['write']

        self.pool_profile = config.get('pool_profile', 'default')
        self.cmd_path = config.get('cmd_path', '/usr/bin/ceph_test_rados')

    def addweight(self, weight):
        value = self.config.get("%s_weight" % weight, None)
        if value is not None:
            self.weights[weight] = int(value)

    # Initialize may only be called once depending on rebuild_every_test setting
    def initialize(self): 
        super(CephTestRados, self).initialize()
        return True

    def run(self):
        self.pre_run()
        
        # Remake the pool
        self.mkpool()
        logger.info('Running ceph_test_rados.')
        ps = []
        for i in xrange(1):
            p = common.pdsh(settings.getnodes('clients'), self.mkcmd())
            ps.append(p)
        for p in ps:
            p.wait()

        self.post_run()

    def mkcmd(self):
        cmd = [self.cmd_path]
        out_file = '%s/output' % self.run_dir

        for flag in ['ec_pool', 'write_fadvise_dontneed', 'pool_snaps']:
            if flag in self.bools:
                cmd.append('--%s' % flag.replace('_', '-'))
        for variable in ['max_ops', 'objects', 'max_in_flight', 'size', 'min_stride_size', 'max_stride_size', 'max_seconds']:
            value = self.variables[variable]
            if value:
                cmd.extend(['--%s' % variable.replace('_', '-'), str(value)])
        for op, weight in self.weights.iteritems():
            cmd.extend(['--op', op, str(weight)])
        cmd.extend(['--pool', 'ceph_test_rados'])
        cmd.extend(['|', 'awk \'{ print strftime("%Y-%m-%d %H:%M:%S"), $0; fflush(); }\'' '>', out_file])
        logger.debug("%s", cmd)
        return ' '.join(cmd)

    def mkpool(self):
        monitoring.start("%s/pool_monitoring" % self.run_dir)
        self.cluster.rmpool('ceph_test_rados', self.pool_profile)
        self.cluster.mkpool('ceph_test_rados', self.pool_profile, 'ceph_test_rados')
        monitoring.stop()

    def recovery_callback(self): 
        common.pdsh(settings.getnodes('clients'), 'sudo pkill -f ceph_test_rados').communicate()

    def __str__(self):
        return "%s\n%s\n%s" % (self.run_dir, self.archive_dir, super(CephTestRados, self).__str__())
