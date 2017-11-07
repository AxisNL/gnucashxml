import locale
import os
import subprocess

from decimal import Decimal

import gnucashxml

gnucashfile = "/Users/angelo/Desktop/paperport/Hongens Automatisering/2017/gnucash/hongens-2017.gnucash"
yearfilter = "2017"
outputfolder = "/Users/angelo/Desktop/paperport/Hongens Automatisering/2017/facturen/tmp"
xelatex_path = "/Library/TeX/texbin/xelatex"


def formatcurrency(amount):
    locale.setlocale(locale.LC_ALL, 'nl_NL.utf-8')
    s = locale.currency(amount, grouping=True, symbol=False)
    s = s.replace(" ", ".")
    return s


def getlatex(invoiceobj):
    latex = ""
    latex += "\\documentclass[a4paper]{letter}\n"
    latex += "\n"
    latex += "\\usepackage{graphicx}\n"
    latex += "\\usepackage{eso-pic}\n"
    latex += "\\usepackage{anysize}\n"
    latex += "\\usepackage{eurosym}\n"
    latex += "\\usepackage{color}\n"
    latex += "\\usepackage{fontspec}\n"
    latex += "\\setmainfont{Lato}\n"
    latex += "\\usepackage{geometry}\n"
    latex += "\\geometry{\n"
    latex += "   paperwidth=210mm,\n"
    latex += "   paperheight=297mm\n"
    latex += "}\n"
    latex += "\\thispagestyle{empty}\n"
    latex += "\n"
    latex += "\\newcommand\\BackgroundPic{\n"
    latex += "  \\put(0,0){\n"
    latex += "  \\parbox[b][\\paperheight]{\\paperwidth}{%\n"
    latex += "  \\vfill\n"
    latex += "  \\centering\n"
    latex += "  \\includegraphics[width=\\paperwidth,height=\\paperheight, keepaspectratio]{back.eps}%\n"
    latex += "  \\vfill\n"
    latex += "  }\n"
    latex += "}}\n"
    latex += "\\marginsize{2cm}{2cm}{0cm}{0cm}\n"
    latex += "\n"
    latex += "\n"
    latex += "\\title{Invoice}\n"
    latex += "\\begin{document}\n"
    latex += "\\AddToShipoutPicture{\\BackgroundPic}\n"
    latex += "\n"
    latex += "%-------------------------------------\n"
    latex += "%ADDRESSEE\n"
    latex += "\\begin{tabular}{ l }\n"
    latex += "  {}\\\\\n".format(invoiceobj.customer.name)
    for addressline in invoiceobj.customer.address:
        addressline = addressline.replace(u'e\u0308', '\\"e')
        latex += "  {} \\\\\n".format(addressline)
    latex += "\n"
    latex += "\\end{tabular}\n"
    latex += "%-------------------------------------\n"
    latex += "\\vspace{1cm}\n"
    latex += "\n"
    latex += "\\LARGE\n"
    latex += "\\textbf{Factuur}\n"
    latex += "\\normalsize\n"
    latex += "\\vspace{0.5cm}\n"
    latex += "\n"
    latex += "\\begin{tabular}{ l l l }\n"
    latex += "  \\textcolor{{gray}}{{Factuurnummer}} & & {} \\\\\n".format(invoiceobj.id)
    latex += "   \\textcolor{{gray}}{{Datum}} & & {0:%d-%m-%Y} \\\\\n".format(invoiceobj.date)
    latex += "   \\textcolor{gray}{Betalingswijze} & & per bank \\\\\n"
    latex += "\\end{tabular}\n"
    latex += "\n"
    latex += "\n"
    latex += "\\vspace{3.5cm}\n"
    latex += "\\large\n"
    latex += "\\textbf{Werkzaamheden}\n"
    latex += "\\normalsize\n"
    latex += "\\vspace{0.5cm}\n"
    latex += "\n"
    latex += "\\hrule\n"
    latex += "%-------------------------------------\n"
    latex += "% WERKZAAMHEDEN\n"
    latex += "%-------------------------------------\n"
    latex += "\\begin{tabular*}{\\textwidth}{@{}@{\\extracolsep{\\fill}} l  r @{}}\n"

    totaalexcl = 0

    btwtabel = {}

    for entry in invoiceobj.entries:
        uren = entry.qty
        tarief = Decimal(entry.price)
        totaalexcl_regel = Decimal(entry.qty * entry.price)
        if int(entry.taxable) == 1:
            taxtable = entry.taxtable
            if len(taxtable.taxtable_entries) > 1:
                print("Error, more than one taxtableentry in taxtable!")
                exit(1)
            taxtableentry = taxtable.taxtable_entries[0]
            btw_tarief_naam = "{0} ({1}\%)".format(taxtable.name, taxtableentry.amount)
            if btw_tarief_naam not in btwtabel.keys():
                btwtabel[btw_tarief_naam] = 0
            btw_hier = Decimal((totaalexcl_regel * taxtableentry.amount)) / 100
            btwtabel[btw_tarief_naam] += btw_hier

        latex += "  {0}, {1} uur \\`a \\EUR{{{2}}}. &  \\EUR{{{3}}}\\\\\n".format(
            entry.description,
            uren,
            formatcurrency(tarief),
            formatcurrency(totaalexcl_regel)
        )
        totaalexcl += totaalexcl_regel
    latex += "\\end{tabular*}\n"
    latex += "%-------------------------------------\n"
    latex += "\\vfill\n"
    latex += "\n"
    latex += "\\hrule\n"
    latex += "\n"
    latex += "\\begin{tabular*}{\\textwidth}{@{}@{\\extracolsep{\\fill}} l  r @{}}\n"
    latex += "  Totaal exclusief BTW & \EUR{{{0}}}\\\\\n".format(formatcurrency(totaalexcl))

    totaalbtw = 0
    for btwkey in btwtabel.keys():
        latex += "  {0}\\ &  \EUR{{{1}}}\\\\\n".format(btwkey, formatcurrency(btwtabel[btwkey]))
        totaalbtw += btwtabel[btwkey]

    latex += "\\end{tabular*}\n"
    latex += "\n"
    latex += "\\hrule\n"
    latex += "\n"
    latex += "\\begin{tabular*}{\\textwidth}{@{}@{\\extracolsep{\\fill}} l  r @{}}\n"

    totaalincl = totaalexcl + totaalbtw
    latex += "  Totaal inclusief BTW &  \EUR{{{0}}}\\\\\n".format(formatcurrency(totaalincl))
    latex += "\\end{tabular*}\n"
    latex += "\n"
    latex += "\\vspace{1cm}\n"
    latex += "\n"
    latex += "Met vriendelijke groet,\n"
    latex += "\n"
    latex += "\\includegraphics[width=40mm]{handtekening.eps}\n"
    latex += "\n"
    latex += "Angelo H\\\"ongens\n"
    latex += "\n"
    latex += "\\vspace{1cm}\n"
    latex += "\n"
    latex += "\\footnotesize\n"
    latex += "Wij verzoeken u vriendelijk bij betaling per bank het bedrag binnen 14 dagen over te maken op bovenstaande bankrekening.\n"
    latex += "\n"
    latex += "\\end{document}\n"
    return latex


def runxelatex(fulltexfilename):
    fullpdffilename = fulltexfilename.replace(".tex", ".pdf")
    if not os.path.exists(fullpdffilename):
        command_line = "{0} \"{1}\"".format(xelatex_path, fulltexfilename)

        print("would run {0}".format(command_line))
        command_result = subprocess.Popen(command_line, stdout=subprocess.PIPE, shell=True, cwd=outputfolder)
        output = command_result.communicate()
        command_exitcode = command_result.returncode
        if command_exitcode == 0:
            print("Successfully created {0}".format(fullpdffilename))
        else:
            print("Error running command '{0}', exit code {1}".format(command_line, command_exitcode))
            print(output)
            exit(1)
    synctextpath = fulltexfilename.replace(".tex", ".synctex.gz")
    if os.path.exists(synctextpath):
        os.remove(synctextpath)
    logpath = fulltexfilename.replace(".tex", ".log")
    if os.path.exists(logpath):
        os.remove(logpath)
    auxpath = fulltexfilename.replace(".tex", ".aux")
    if os.path.exists(auxpath):
        os.remove(auxpath)


# begin
book = gnucashxml.from_filename(gnucashfile)
for invoice in book.invoices:
    if invoice.customer is not None:
        if yearfilter in invoice.id:
            latexcontent = getlatex(invoice)
            filename = "{0} {1}.tex".format(invoice.id, invoice.customer.name)
            fullpath = os.path.join(outputfolder, filename)
            with open(fullpath, 'w') as outfile:
                outfile.write(latexcontent)
            runxelatex(fullpath)
