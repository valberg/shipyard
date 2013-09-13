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
from django.shortcuts import render_to_response, redirect
from django.contrib.auth.decorators import login_required
from django.template import RequestContext
from django.contrib import messages
from django.utils.translation import ugettext as _
from hosts.models import Host


@login_required
def index(request):
    hosts = Host.objects.filter(enabled=True)
    images = {}
    for h in hosts:
        images[h] = h.get_images()
    ctx = {
        'images': images
    }
    return render_to_response('images/index.html', ctx,
        context_instance=RequestContext(request))

@login_required
def remove_image(request, host_id, image_id):
    h = Host.objects.get(id=host_id)
    h.remove_image(image_id)
    messages.add_message(request, messages.INFO, _('Removed') + ' {0}'.format(
        image_id))
    return redirect('images.views.index')

