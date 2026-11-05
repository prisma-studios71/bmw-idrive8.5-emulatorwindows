import pathlib
import subprocess
import xml.etree.ElementTree as ET


base = pathlib.Path('/mnt/hmi8-lab/ivi-controller-legacy')
output = pathlib.Path('/srv/hmi8-lab/controller-bridge')
output.mkdir(parents=True, exist_ok=True)
protocol = base / 'protocol/ivi-controller.xml'
for operation, filename in [('server-header', 'protocol.h'), ('private-code', 'protocol.c')]:
    subprocess.run(['wayland-scanner', operation, str(protocol), str(output / filename)], check=True)

prefix = r'''
#include <stdint.h>
#include <stdlib.h>
#include <wayland-server.h>
#include <libweston/libweston.h>
#include <weston.h>
#include <ivi-layout-export.h>
#include "protocol.h"
static const struct ivi_layout_interface *layout;
static struct weston_compositor *compositor;
static struct ivi_layout_layer *main_layer;
static struct wl_listener created_listener, configured_listener;
static struct wl_list controllers;
struct controller_client { struct wl_list link; struct wl_resource *resource; };
static const struct ivi_controller_surface_interface surface_handlers;
static const struct ivi_controller_layer_interface layer_handlers;
static const struct ivi_controller_screen_interface screen_handlers;
static uint32_t object_id(struct wl_resource *resource) {
    return (uint32_t)(uintptr_t)wl_resource_get_user_data(resource);
}
static void auto_layout(struct wl_listener *listener, void *data) {
    struct ivi_layout_surface *surface = data;
    struct weston_output *screen;
    int32_t width = 0, height = 0, stride = 0;
    layout->surface_get_size(surface, &width, &height, &stride);
    if (width <= 0 || height <= 0 || wl_list_empty(&compositor->output_list)) return;
    screen = wl_container_of(compositor->output_list.next, screen, link);
    if (!main_layer) {
        main_layer = layout->layer_create_with_dimension(9000, screen->width, screen->height);
        layout->layer_set_visibility(main_layer, true);
        layout->layer_set_source_rectangle(main_layer, 0, 0, screen->width, screen->height);
        layout->layer_set_destination_rectangle(main_layer, 0, 0, screen->width, screen->height);
        layout->screen_add_layer(screen, main_layer);
    }
    layout->layer_add_surface(main_layer, surface);
    layout->surface_set_source_rectangle(surface, 0, 0, width, height);
    layout->surface_set_destination_rectangle(surface, 0, 0, screen->width, screen->height);
    layout->surface_set_visibility(surface, true);
    layout->commit_changes();
    weston_log("LAB bridge: configured real surface %u (%dx%d)\n", layout->get_id_of_surface(surface), width, height);
}
static void surface_created(struct wl_listener *listener, void *data) {
    struct controller_client *client;
    weston_log("LAB bridge: created surface %u\n", layout->get_id_of_surface(data));
    wl_list_for_each(client, &controllers, link)
        ivi_controller_send_surface(client->resource, layout->get_id_of_surface(data));
}
static void controller_destroyed(struct wl_resource *resource) {
    struct controller_client *client = wl_resource_get_user_data(resource);
    wl_list_remove(&client->link);
    free(client);
}
'''

bodies = {
    ('ivi_controller', 'commit_changes'): 'layout->commit_changes();',
    ('ivi_controller', 'surface_create'): r'''
struct wl_resource *child = wl_resource_create(client, &ivi_controller_surface_interface, 1, id);
wl_resource_set_implementation(child, &surface_handlers, (void *)(uintptr_t)id_surface, NULL);
ivi_controller_surface_send_visibility(child, 1);
''',
    ('ivi_controller', 'layer_create'): r'''
struct ivi_layout_layer *layer = layout->layer_create_with_dimension(id_layer, width, height);
struct wl_resource *child = wl_resource_create(client, &ivi_controller_layer_interface, 1, id);
wl_resource_set_implementation(child, &layer_handlers, (void *)(uintptr_t)id_layer, NULL);
if (layer) layout->layer_set_visibility(layer, true);
''',
    ('ivi_controller_layer', 'add_surface'): r'''
struct ivi_layout_layer *layer = layout->get_layer_from_id(object_id(resource));
struct ivi_layout_surface *target = layout->get_surface_from_id(object_id(surface));
if (layer && target) layout->layer_add_surface(layer, target);
''',
    ('ivi_controller_screen', 'add_layer'): r'''
struct weston_output *screen = wl_resource_get_user_data(resource);
struct ivi_layout_layer *target = layout->get_layer_from_id(object_id(layer));
if (screen && target) layout->screen_add_layer(screen, target);
''',
}

for kind in ['surface', 'layer']:
    for method, arguments in [
        ('set_visibility', 'visibility'), ('set_opacity', 'opacity'),
        ('set_source_rectangle', 'x, y, width, height'),
        ('set_destination_rectangle', 'x, y, width, height'),
    ]:
        bodies[(f'ivi_controller_{kind}', method)] = (
            f'struct ivi_layout_{kind} *target = layout->get_{kind}_from_id(object_id(resource));\n'
            f'if (target) layout->{kind}_{method}(target, {arguments});'
        )

types = {'uint': 'uint32_t', 'int': 'int32_t', 'fixed': 'wl_fixed_t',
         'string': 'const char *', 'object': 'struct wl_resource *',
         'new_id': 'uint32_t', 'array': 'struct wl_array *', 'fd': 'int32_t'}
parts = [prefix]
for interface in ET.parse(protocol).getroot().findall('interface'):
    name = interface.attrib['name']
    handlers = []
    for request in interface.findall('request'):
        method = request.attrib['name']
        arguments = ['struct wl_client *client', 'struct wl_resource *resource']
        arguments += [f"{types[arg.attrib['type']]} {arg.attrib['name']}" for arg in request.findall('arg')]
        body = bodies.get((name, method))
        if body is None:
            body = 'wl_resource_destroy(resource);' if method == 'destroy' else f'weston_log("LAB bridge: unsupported {name}.{method}\\n");'
        function = f'{name}_{method}_handler'
        if method != 'commit_changes':
            trace_fields = []
            trace_values = []
            for argument in request.findall('arg'):
                argument_name = argument.attrib['name']
                argument_type = argument.attrib['type']
                trace_fields.append(f"{argument_name}={'%s' if argument_type == 'string' else '%u' if argument_type in ('uint', 'new_id') else '%d' if argument_type in ('int', 'fixed') else '%p'}")
                trace_values.append(f'({argument_name} ? {argument_name} : "")' if argument_type == 'string' else f'(void *){argument_name}' if argument_type in ('object', 'array') else argument_name)
            suffix = ', ' + ', '.join(trace_values) if trace_values else ''
            body = ('pid_t client_pid;\n'
                    'wl_client_get_credentials(client, &client_pid, NULL, NULL);\n'
                    f'weston_log("LAB request pid=%d {name}.{method} resource=%u {" ".join(trace_fields)}\\n", '
                    f'client_pid, wl_resource_get_id(resource){suffix});\n' + body)
        parts.append(f'static void {function}({", ".join(arguments)}) {{\n{body}\n}}\n')
        handlers.append(f'.{method} = {function}')
    short = name.removeprefix('ivi_controller_')
    table = 'controller_handlers' if name == 'ivi_controller' else f'{short}_handlers'
    parts.append(f'static const struct {name}_interface {table} = {{ {", ".join(handlers)} }};\n')

parts.append(r'''
static void bind_controller(struct wl_client *client, void *data, uint32_t version, uint32_t id) {
    struct controller_client *entry = calloc(1, sizeof *entry);
    struct weston_output *screen;
    struct ivi_layout_surface **surfaces = NULL;
    int32_t count = 0;
    entry->resource = wl_resource_create(client, &ivi_controller_interface, 1, id);
    wl_resource_set_implementation(entry->resource, &controller_handlers, entry, controller_destroyed);
    wl_list_insert(&controllers, &entry->link);
    wl_list_for_each(screen, &compositor->output_list, link) {
        struct wl_resource *child = wl_resource_create(client, &ivi_controller_screen_interface, 1, 0);
        wl_resource_set_implementation(child, &screen_handlers, screen, NULL);
        ivi_controller_send_screen(entry->resource, screen->id, child);
    }
    layout->get_surfaces(&count, &surfaces);
    for (int index = 0; index < count; index++)
        ivi_controller_send_surface(entry->resource, layout->get_id_of_surface(surfaces[index]));
    free(surfaces);
}
WL_EXPORT int wet_module_init(struct weston_compositor *instance, int *argc, char *argv[]) {
    compositor = instance;
    layout = ivi_layout_get_api(instance);
    if (!layout) return -1;
    wl_list_init(&controllers);
    created_listener.notify = surface_created;
    configured_listener.notify = auto_layout;
    layout->add_listener_create_surface(&created_listener);
    layout->add_listener_configure_surface(&configured_listener);
    if (!wl_global_create(instance->wl_display, &ivi_controller_interface, 1, NULL, bind_controller)) return -1;
    weston_log("LAB bridge: legacy ivi_controller v1; partial API with automatic visibility\n");
    return 0;
}
''')
(output / 'bridge.c').write_text('\n'.join(parts))
flags = subprocess.check_output(['pkg-config', '--cflags', '--libs', 'weston', 'libweston-13', 'wayland-server'], text=True).split()
subprocess.run(['cc', '-shared', '-fPIC', '-O2', '-Wall', '-Werror=implicit-function-declaration', '-o', str(output / 'lab-ivi-controller.so'), str(output / 'bridge.c'), str(output / 'protocol.c'), *flags], check=True)
