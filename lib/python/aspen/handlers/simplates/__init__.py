"""Three-part resources.

Simplates
Triplates

thin wedge to allow a simplate to handle all requests for at or below a given
directory: nope, use middleware for that to rewrite URLs and pass through

========================================
    User's POV
========================================

1. install framework

    $ easy_install django


2. configure framework

    $ django-admin.py startproject foo
    $ vi foo/settings.py


3. wire framework in aspen.conf

    [django]
    settings_module = foo.settings


4. wire up handlers.conf

    [aspen.handlers.simplates:django
    fnmatch *.html


5. GGG!


========================================
    Request Processing
========================================

request comes in, matches simplates:<framework> in handlers.conf
control passes to aspen.handlers.simplates:<framework>
simplates:<framework> loads the simplate from a cache
    cache is global to Aspen handlers (static only other?)
    cache is tunable by mem-size, max obj size
    cache invalidates on tunables + resource modtime
    cache is thread-safe
    cache builds simplate
        import section is always built and run the same
        script section is always built the same, but is run differently
        template section needs to be built differently for each type (but buffet?)
simplates:wsgi runs the script
    namespace population is framework-specific
    raise SystemExit => stop script, proceed to template
    raise SystemExit(response) => stop script, skip template, return response
        response obj is framework-specific
    @@: allow multiple frameworks in one simplate?
simplates:wsgi renders the template
    uses buffet's render API
        need a Buffet wrapper for Django and ZPT, eh?
    building contexts will differ by framework
simplates:wsgi converts response/rendered template to WSGI return val


"""

import threading

from aspen import mode


FORM_FEED = chr(12) # ^L, ASCII page break






class Cache(object):
    """A simple thread-safe cache; values never expire.
    """

    def __init__(self, build):
        """
        """
        self.build = build
        self.cache = dict()
        self.lock = threading.Lock()

    if (mode is not None) and mode.DEVDEB:              # uncached
        def __getitem__(self, key):
            """Key access always calls build.
            """
            return self.build(key)

    else:                                               # cached
        def __getitem__(self, key):
            """Key access only calls build the first time.
            """
            if key not in self.cache:
                self.lock.acquire()
                try: # critical section
                    if key not in self.cache: # were we in fact blocking?
                        self.cache[key] = self.build(key)
                finally:
                    self.lock.release()
            return self.cache[key]


    def build(fspath):
        """Given a filesystem path, return a compiled (but unbound) object.

        A simplate is a template with two optional Python components at the head
        of the file, delimited by an ASCII form feed (also called a page break, FF,
        ^L, \x0c, 12). The first Python section is exec'd when the simplate is
        first called, and the namespace it populates is saved for all subsequent
        runs (so make sure it is thread-safe!). The second Python section is exec'd
        within the template namespace each time the template is rendered.

        It is a requirement that subclasses do not mutate the import context at
        runtime.

        """
        simplate = open(fspath).read()

        numff = simplate.count(FORM_FEED)
        if numff == 0:
            script = imports = ""
            template = simplate
        elif numff == 1:
            imports = ""
            script, template = simplate.split(FORM_FEED)
        elif numff == 2:
            imports, script, template = simplate.split(FORM_FEED)
        else:
            raise SyntaxError( "Simplate <%s> may have at most two " % fspath
                             + "form feeds; it has %d." % numff
                              )

        # Standardize newlines.
        # =====================
        # compile requires \n, and doing it now makes the next line easier.

        imports = imports.replace('\r\n', '\n')
        script = script.replace('\r\n', '\n')


        # Pad the beginning of the script section so we get accurate tracebacks.
        # ======================================================================

        script = ''.join(['\n' for n in range(imports.count('\n')-2)]) + script


        # Prep our cachable objects and return.
        # =====================================

        c_imports = dict()
        exec compile(imports, fspath, 'exec') in c_imports
        c_script = compile(script, fspath, 'exec')
        c_template = self.build_template(template)

        return (c_imports, c_script, c_template)


    def view(self, request):
        """Django view to exec and render the simplate at PATH_TRANSLATED.

        Your script section may raise SystemExit to terminate execution. Instantiate
        the SystemExit with an HttpResponse to bypass template rendering entirely;
        in all other cases, the template section will still be rendered.

        """
        imports, script, template = cache[request.META['PATH_TRANSLATED']]

        template_context = RequestContext(request, imports)

        if script:
            script_context = dict()
            for d in template_context.dicts:
                script_context.update(d)
            try:
                exec script in script_context
            except SystemExit, exc:
                if len(exc.args) >= 1:
                    response = exc.args[0]
                    if isinstance(response, HttpResponse):
                        return response
            template_context.update(script_context)

        response = HttpResponse(template.render(template_context))
        del response.headers['Content-Type'] # take this from the extension
        return response