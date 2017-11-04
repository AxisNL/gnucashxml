import json
import gnucashxml

gnucashfile = "/Users/angelo/Desktop/paperport/Hongens Automatisering/2017/gnucash/hongens-2017.gnucash"
yearfilter = "2017"
outputfolder = "/Users/angelo/Desktop/paperport/Hongens Automatisering/2017/facturen/tmp"
xelatex_path = "/Library/TeX/texbin/xelatex"

# begin
book = gnucashxml.from_filename(gnucashfile)
for invoice in book.invoices:
    if invoice.customer is not None:
        if "2017" in invoice.id:
            print json.dumps(invoice, cls=gnucashxml.CustomJSONEncoder, indent=4)
