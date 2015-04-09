"""
Sublime Text 2 Plugin to invoke Yapf on a python file.
"""

import ConfigParser
import os
import subprocess
import tempfile
import codecs

import sublime, sublime_plugin

KEY = "pyyapf"


def failure_parser(in_failure):
    """
    Parse the last line of a yapf traceback into something
    we can use (preferable row/column)
    """
    if isinstance(in_failure, UnicodeEncodeError):
        # so much easier when we have the actual exception
        err = in_failure.reason
        msg = in_failure.message
        tval = {'context': "(\"\", %i)" % in_failure.start}
    else:
        # we got a string error from yapf
        #
        lastline = in_failure.strip().split('\n')[-1]
        err, msg = lastline.split(':')[0:2]
        detail = ":".join(lastline.strip().split(':')[2:])
        tval = {}
        stripped_comma = False
        key = None

        if err == "UnicodeEncodeError":
            # UnicodeEncodeError
            # 'ascii' codec can't encode characters in position 175337-175339
            # ordinal not in range(128)
            position = msg.split('-')[-1]
            tval = {'context': "(\"\", %i)" % int(position)}
        else:
            for element in detail.split(' '):
                element = element.strip()
                if not element:
                    continue
                if "=" in element:
                    key, value = element.split('=')
                    stripped_comma = value[-1] == ","
                    value = value.rstrip(',')
                    tval[key] = value
                else:
                    if stripped_comma:
                        element = ", " + element
                    stripped_comma = False
                    tval[key] += element

    return err, msg, tval


def save_style_to_tempfile(in_dict):
    """
    Take a dictionary of yapf style settings and return the file
    name of a tempfile containing the expected config formatted
    style settings
    """

    cfg = ConfigParser.RawConfigParser()
    cfg.add_section('style')
    for key in in_dict:
        cfg.set('style', key, in_dict[key])

    fobj, filename = tempfile.mkstemp()
    cfg.write(os.fdopen(fobj, "w"))
    return filename

# pylint: disable=W0232
class YapfCommand(sublime_plugin.TextCommand):
    """
    This is the actual class instantated by Sublime when
    the command 'yapf' is invoked.
    """
    view = None

    def smart_failure(self, in_failure):
        """
        Take a failure exception or the stderr from yapf
        and try to extract useful information like what kind
        of problem is it and where in your code the problem is.
        """
        err, msg, context_dict = failure_parser(in_failure)

        sublime.error_message("{0}\n{1}\n\n{2}".format(err, msg,
                                                       repr(context_dict)))

        if 'context' in context_dict:
            #"('', (46,44))"
            rowcol = context_dict['context'][1:-1]

            # ignore the first arg
            rowcol = rowcol[rowcol.find(',') + 1:].strip()
            if rowcol[0] == "(":
                rowcol = rowcol[1:-1]  # remove parens
                row, col = rowcol.split(',')
                col = int(col)
                row = int(row)

                point = self.view.text_point(row - 1, col - 1)
                print('centering on row: %r, col: %r' % (row - 1, col - 1))
            else:
                point = int(rowcol)
                print('centering on character index %r' % point)

            # clear any existing pyyapf markers
            #pyyapf_regions = self.view.get_regions(KEY)
            self.view.erase_regions(KEY)

            scope = "pyyapf"
            region = self.view.line(point)
            self.view.add_regions(KEY, [region], scope, "dot")
            self.view.show_at_center(region)

            print(repr(in_failure))

    def save_selection_to_tempfile(self, selection, encoding):
        """
        dump the current selection to a tempfile
        and return the filename.  caller is responsible
        for cleanup.
        """
        fobj, filename = tempfile.mkstemp(suffix=".py")
        temphandle = os.fdopen(fobj, 'w')
        try:
            encoded = self.view.substr(selection).encode(encoding)
        except UnicodeEncodeError as err:
            self.smart_failure(err)
            return

        temphandle.write(encoded)
        temphandle.close()
        return filename

    def run(self, edit):
        """
        primary action when the plugin is triggered
        """
        print("Formatting selection with Yapf")

        encoding = self.view.encoding()
        if encoding == "Undefined":
            encoding = "ascii"

        print('Using encoding of %r' % encoding)

        settings = sublime.load_settings("PyYapf.sublime-settings")

        for region in self.view.sel():
            if region.empty():
                if settings.get("use_entire_file_if_no_selection", True):
                    selection = sublime.Region(0, self.view.size())
                else:
                    sublime.error_message('A selection is required')
                    selection = None
            else:
                selection = region

            if selection:
                py_filename = self.save_selection_to_tempfile(selection,
                                                              encoding)

                style_filename = save_style_to_tempfile(
                    settings.get("config", {}))
                yapf = settings.get("yapf_command", "/usr/local/bin/yapf")
                cmd = [yapf, "--style={0}".format(style_filename), "--verify",
                       "--in-place", py_filename]

                print('Running {0}'.format(cmd))
                proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)

                output, output_err = proc.communicate()
                #self.view.substr(selection).encode('utf-8')
                #)
                temphandle = codecs.open(py_filename, encoding=encoding)
                output = temphandle.read()
                temphandle.close()

                if output_err == "":
                    self.view.replace(edit, selection, output)
                else:
                    try:
                        self.smart_failure(output_err)

                    # Catching too general exception
                    # pylint: disable=W0703
                    except Exception as err:
                        print('Unable to parse %r', err)
                        sublime.error_message(output_err)

                os.unlink(py_filename)
                os.unlink(style_filename)

        print('PyYapf Completed')
