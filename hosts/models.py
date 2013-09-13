import hashlib
import json
from containers.models import Container
from shipyard import utils
from docker import client
from django.core.cache import cache
from django.conf import settings
from django.db import models
import requests


HOST_CACHE_TTL = getattr(settings, 'HOST_CACHE_TTL', 15)
CONTAINER_KEY = '{0}:containers'
IMAGE_KEY = '{0}:images'


class Host(models.Model):
    name = models.CharField(max_length=64, null=True,
        unique=True)
    hostname = models.CharField(max_length=128, null=True,
        unique=True)
    port = models.SmallIntegerField(null=True, default=4243)
    enabled = models.NullBooleanField(null=True, default=True)

    def __unicode__(self):
        return self.name

    def _get_client(self):
        url ='{0}:{1}'.format(self.hostname, self.port)
        if not url.startswith('http'):
            url = 'http://{0}'.format(url)
        return client.Client(url)

    def _invalidate_container_cache(self):
        # invalidate cache
        key = CONTAINER_KEY.format(self.name)
        cache.delete_pattern('*{0}*'.format(key))

    def _invalidate_image_cache(self):
        # invalidate cache
        cache.delete(IMAGE_KEY.format(self.name))

    def _generate_container_cache_key(self, seed=None):
        gen_id = hashlib.sha224(self.name + str(seed)).hexdigest()
        key = '{0}:{1}'.format(CONTAINER_KEY.format(self.name), gen_id)
        return key

    def invalidate_cache(self):
        self._invalidate_container_cache()
        self._invalidate_image_cache()

    def get_containers(self, show_all=False):
        c = client.Client(base_url='http://{0}:{1}'.format(self.hostname,
            self.port))
        key = self._generate_container_cache_key(show_all)
        containers = cache.get(key)
        container_ids = []
        if containers is None:
            try:
                containers = c.containers(all=show_all)
            except requests.ConnectionError:
                containers = []
            # update meta data
            for x in containers:
                # only get first 12 chars of id (for metatdata)
                c_id = utils.get_short_id(x.get('Id'))
                # ignore stopped containers
                meta = c.inspect_container(c_id)
                m, created = Container.objects.get_or_create(
                    container_id=c_id, host=self)
                m.is_running = meta.get('State', {}).get('Running', False)
                m.meta = json.dumps(meta)
                m.save()
                container_ids.append(c_id)
            # set extra containers to not running
            Container.objects.filter(host=self).exclude(
                container_id__in=container_ids).update(is_running=False)
            cache.set(key, containers, HOST_CACHE_TTL)
        return containers

    def get_containers_for_user(self, user=None, show_all=False):
        containers = self.get_containers(show_all=show_all)
        # don't filter staff
        if user.is_staff:
            return containers
        # filter
        ids = [x.container_id for x in Container.objects.all() \
            if x.owner == None or x.owner == user]
        return [x for x in containers if x.get('Id') in ids]

    def get_images(self, show_all=False):
        c = client.Client(base_url='http://{0}:{1}'.format(self.hostname,
            self.port))
        key = IMAGE_KEY.format(self.name)
        images = cache.get(key)
        if images is None:
            try:
                # only show images with a repository name
                images = [x for x in c.images(all=show_all) if x.get('Repository')]
                cache.set(key, images, HOST_CACHE_TTL)
            except requests.ConnectionError:
                images = []
        return images

    def create_container(self, image=None, command=None, ports=[],
        environment=[], memory=0, description='', volumes=[],
        volumes_from='', privileged=False, owner=None):
        c = self._get_client()
        cnt = c.create_container(image, command, detach=True, ports=ports,
            mem_limit=memory, tty=True, stdin_open=True,
            environment=environment, volumes=volumes, volumes_from=volumes_from,
            privileged=privileged)
        c_id = cnt.get('Id')
        c.start(c_id)
        status = False
        # create metadata only if container starts successfully
        if c.inspect_container(c_id).get('State', {}).get('Running'):
            c, created = Container.objects.get_or_create(container_id=c_id,
                host=self)
            c.description = description
            c.owner = owner
            c.save()
            status = True
        # clear host cache
        self._invalidate_container_cache()
        return c_id, status

    def restart_container(self, container_id=None):
        from applications.models import Application
        c = self._get_client()
        c.restart(container_id)
        self._invalidate_container_cache()
        # reload containers to get proper port
        self.get_containers()
        # update hipache
        apps = Application.objects.filter(containers__in=[self])
        for app in apps:
            app.update_config()

    def stop_container(self, container_id=None):
        c = self._get_client()
        c.stop(container_id)
        self._invalidate_container_cache()

    def get_container_logs(self, container_id=None):
        c = self._get_client()
        return c.logs(container_id)

    def destroy_container(self, container_id=None):
        c = self._get_client()
        c_id = utils.get_short_id(container_id)
        c.kill(c_id)
        c.remove_container(c_id)
        # remove metadata
        Container.objects.filter(container_id=c_id).delete()
        self._invalidate_container_cache()

    def import_image(self, repository=None):
        c = self._get_client()
        c.pull(repository)
        self._invalidate_image_cache()

    def build_image(self, docker_file=None, tag=None):
        c = self._get_client()
        f = open(docker_file, 'r')
        c.build(f, tag)

    def remove_image(self, image_id=None):
        c = self._get_client()
        c.remove_image(image_id)
        self._invalidate_image_cache()