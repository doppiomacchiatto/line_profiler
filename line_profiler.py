#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from cStringIO import StringIO
import inspect
import linecache
import marshal
import optparse
import os
import sys

from _line_profiler import LineProfiler as CLineProfiler


class LineProfiler(CLineProfiler):
    """ A profiler that records the execution times of individual lines.
    """

    def __call__(self, func):
        """ Decorate a function to start the profiler on function entry and stop
        it on function exit.
        """
        def f(*args, **kwds):
            self.add_function(func)
            self.enable_by_count()
            try:
                result = func(*args, **kwds)
            finally:
                self.disable_by_count()
            return result
        f.__name__ = func.__name__
        f.__doc__ = func.__doc__
        f.__dict__.update(func.__dict__)
        return f

    def dump_stats(self, filename):
        """ Dump a representation of the data to a file as a marshalled
        dictionary from `get_stats()`.
        """
        stats, unit = self.get_stats()
        f = open(filename, 'wb')
        try:
            marshal.dump((stats, unit), f)
        finally:
            f.close()

    def print_stats(self, stream=None):
        """ Show the gathered statistics.
        """
        stats, unit = self.get_stats()
        show_text(stats, unit, stream=stream)

    def run(self, cmd):
        """ Profile a single executable statment in the main namespace.
        """
        import __main__
        dict = __main__.__dict__
        return self.runctx(cmd, dict, dict)

    def runctx(self, cmd, globals, locals):
        """ Profile a single executable statement in the given namespaces.
        """
        self.enable_by_count()
        try:
            exec cmd in globals, locals
        finally:
            self.disable_by_count()
        return self

    def runcall(self, func, *args, **kw):
        """ Profile a single function call.
        """
        self.enable_by_count()
        try:
            return func(*args, **kw)
        finally:
            self.disable_by_count()


def show_func(filename, start_lineno, func_name, timings, unit, stream=None):
    """ Show results for a single function.
    """
    if stream is None:
        stream = sys.stdout
    if not os.path.exists(filename):
        print >>stream, 'Could not find file %s' % filename
        print >>stream, 'Are you sure you are running this program from the same directory'
        print >>stream, 'that you ran the profiler from?'
        return
    print >>stream, 'File: %s' % filename
    print >>stream, 'Function: %s at line %s' % (func_name, start_lineno)
    all_lines = linecache.getlines(filename)
    sublines = inspect.getblock(all_lines[start_lineno-1:])
    template = '%6s %9s %12s %8s %8s  %-s'
    d = {}
    total_time = 0.0
    for lineno, nhits, time in timings:
        total_time += time
    print >>stream, 'Total time: %g s' % (total_time * unit)
    for lineno, nhits, time in timings:
        d[lineno] = (nhits, time, '%6g' % (float(time) / nhits), '%5.1f' % (100*time / total_time))
    linenos = range(start_lineno, start_lineno + len(sublines))
    empty = ('', '', '', '')
    header = template % ('Line #', 'Hits', 'Time', 'Per Hit', '% Time', 'Line Contents')
    print >>stream, ''
    print >>stream, header
    print >>stream, '=' * len(header)
    for lineno, line in zip(linenos, sublines):
        nhits, time, per_hit, percent = d.get(lineno, empty)
        print >>stream, template % (lineno, nhits, time, per_hit, percent, line.rstrip('\n').rstrip('\r'))
    print >>stream, ''

def show_text(stats, unit, stream=None):
    """ Show text for the given timings.
    """
    if stream is None:
        stream = sys.stdout
    print >>stream, 'Timer unit: %g s' % unit
    print >>stream, ''
    for (fn, lineno, name), timings in sorted(stats.items()):
        show_func(fn, lineno, name, stats[fn, lineno, name], unit, stream=stream)

# A %lprun magic for IPython.
def magic_lprun(self, parameter_s=''):
    """ Execute a statement under the line-by-line profiler from the
    line_profiler module.

    Usage:
      %lprun -f func1 -f func2 <statement>

    The given statement (which doesn't require quote marks) is run via the
    LineProfiler. Profiling is enabled for the functions specified by the -f
    options. The statistics will be shown side-by-side with the code through the
    pager once the statement has completed.

    Options:
    
    -f <function>: LineProfiler only profiles functions and methods it is told
    to profile.  This option tells the profiler about these functions. Multiple
    -f options may be used. The argument may be any expression that gives
    a Python function or method object. However, one must be careful to avoid
    spaces that may confuse the option parser. Additionally, functions defined
    in the interpreter at the In[] prompt or via %run currently cannot be
    displayed.  Write these functions out to a separate file and import them.

    One or more -f options are required to get any useful results.

    -D <filename>: dump the raw statistics out to a marshal file on disk. The
    usual extension for this is ".lprof". These statistics may be viewed later
    by running line_profiler.py as a script.

    -T <filename>: dump the text-formatted statistics with the code side-by-side
    out to a text file.

    -r: return the LineProfiler object after it has completed profiling.
    """
    # Local import to avoid hard dependency.
    from IPython.genutils import page
    from IPython.ipstruct import Struct
    from IPython.ipapi import UsageError

    # Escape quote markers.
    opts_def = Struct(D=[''], T=[''], f=[])
    parameter_s = parameter_s.replace('"',r'\"').replace("'",r"\'")
    opts, arg_str = self.parse_options(parameter_s, 'rf:D:T:', list_all=True)
    opts.merge(opts_def)

    global_ns = self.shell.user_global_ns
    local_ns = self.shell.user_ns

    # Get the requested functions.
    funcs = []
    for name in opts.f:
        try:
            funcs.append(eval(name, global_ns, local_ns))
        except Exception, e:
            raise UsageError('Could not find function %r.\n%s: %s' % (name, 
                e.__class__.__name__, e))

    profile = LineProfiler(*funcs)

    # Add the profiler to the builtins for @profile.
    import __builtin__
    if 'profile' in __builtin__.__dict__:
        had_profile = True
        old_profile = __builtin__.__dict__['profile']
    else:
        had_profile = False
        old_profile = None
    __builtin__.__dict__['profile'] = profile

    try:
        try:
            profile.runctx(arg_str, global_ns, local_ns)
            message = ''
        except SystemExit:
            message = """*** SystemExit exception caught in code being profiled."""
        except KeyboardInterrupt:
            message = ("*** KeyboardInterrupt exception caught in code being "
                "profiled.")
    finally:
        if had_profile:
            __builtin__.__dict__['profile'] = old_profile

    # Trap text output.
    stdout_trap = StringIO()
    profile.print_stats(stdout_trap)
    output = stdout_trap.getvalue()
    output = output.rstrip()

    page(output, screen_lines=self.shell.rc.screen_length)
    print message,

    dump_file = opts.D[0]
    if dump_file:
        profile.dump_stats(dump_file)
        print '\n*** Profile stats marshalled to file',\
              `dump_file`+'.',message

    text_file = opts.T[0]
    if text_file:
        pfile = open(text_file, 'w')
        pfile.write(output)
        pfile.close()
        print '\n*** Profile printout saved to text file',\
              `text_file`+'.',message

    return_value = None
    if opts.has_key('r'):
        return_value = profile

    return return_value


def main():
    usage = "usage: %prog profile.lprof"
    parser = optparse.OptionParser(usage)

    options, args = parser.parse_args()
    if len(args) != 1:
        parser.error("Must provide a filename.")
    f = open(args[0], 'rb')
    stats, unit = marshal.load(f)
    f.close()
    show_text(stats, unit)

if __name__ == '__main__':
    main()
