# Copyright 2013 Evan Hazlett and contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json

from django.db import models
from django.contrib.auth.models import User
from docker import client
from django.conf import settings
from django.db.models import Q
from docker import client
from django.core.cache import cache
from hosts.models import Host
from shipyard import utils
import requests


HOST_CACHE_TTL = getattr(settings, 'HOST_CACHE_TTL', 15)
CONTAINER_KEY = '{0}:containers'
IMAGE_KEY = '{0}:images'


class Container(models.Model):
    container_id = models.CharField(max_length=96, null=True, blank=True)
    description = models.TextField(blank=True, null=True, default='')
    meta = models.TextField(blank=True, null=True, default='{}')
    is_running = models.BooleanField(default=True)
    host = models.ForeignKey(Host, null=True, blank=True)
    owner = models.ForeignKey(User, null=True, blank=True)

    def __unicode__(self):
        d = self.container_id
        if self.description:
            d += ' ({0})'.format(self.description)
        return d

    @classmethod
    def get_running(cls, user=None):
        hosts = Host.objects.filter(enabled=True)
        containers = None
        if hosts:
            c_ids = []
            for h in hosts:
                for c in h.get_containers():
                    c_ids.append(utils.get_short_id(c.get('Id')))
            # return metadata objects
            containers = Container.objects.filter(container_id__in=c_ids).filter(
                Q(owner=None))
            if user:
                containers = containers.filter(Q(owner=request.user))
        return containers

    def is_public(self):
        if self.user == None:
            return True
        else:
            return False

    def get_meta(self):
        return json.loads(self.meta)

    def get_ports(self):
        meta = self.get_meta()
        port_mapping = meta.get('NetworkSettings', {}).get('PortMapping')
        if port_mapping:
            return port_mapping.get('Tcp', {})
        return None

    def get_memory_limit(self):
        mem = 0
        meta = self.get_meta()
        if meta:
            mem = int(meta.get('Config', {}).get('Memory')) / 1048576
        return mem

    def get_name(self):
        d = self.container_id
        if self.description:
            d = self.description
        return d
