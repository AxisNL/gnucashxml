# gnucashxml.py --- Parse GNU Cash XML files

# Copyright (C) 2012 Jorgen Schaefer <forcer@forcix.cx>
#           (C) 2017 Christopher Lam
#           (C) 2017 Angelo Hongens

# Author: Jorgen Schaefer <forcer@forcix.cx>
#         Christopher Lam <https://github.com/christopherlam>
#         Angelo Hongens <https://github.com/AxisNL>

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import decimal
import gzip
import json
import datetime
from dateutil.parser import parse as parse_date

try:
    import lxml.etree as ElementTree
except:
    from xml.etree import ElementTree
from xml.etree.ElementTree import ParseError

__version__ = "1.1"


class Book(object):
    """
    A book is the main container for GNU Cash data.

    It doesn't really do anything at all by itself, except to have
    a reference to the accounts, transactions, prices, and commodities.
    """

    def __init__(self, tree, guid, prices=None, transactions=None, root_account=None,
                 accounts=None, commodities=None, slots=None, invoices=None):
        self.tree = tree
        self.guid = guid
        self.prices = prices
        self.transactions = transactions or []
        self.root_account = root_account
        self.accounts = accounts or []
        self.commodities = commodities or []
        self.slots = slots or {}
        self.invoices = invoices or []

    def __repr__(self):
        return "<Book {}>".format(self.guid)

    def walk(self):
        return self.root_account.walk()

    def find_account(self, name):
        for account, children, splits in self.walk():
            if account.name == name:
                return account

    def find_guid(self, guid):
        for item in self.accounts + self.transactions:
            if item.guid == guid:
                return item

    def ledger(self):
        outp = []

        for comm in self.commodities:
            outp.append('commodity {}'.format(comm.name))
            outp.append('\tnamespace {}'.format(comm.space))
            outp.append('')

        for account in self.accounts:
            outp.append('account {}'.format(account.fullname()))
            if account.description:
                outp.append('\tnote {}'.format(account.description))
            outp.append('\tcheck commodity == "{}"'.format(account.commodity))
            outp.append('')

        for trn in sorted(self.transactions):
            outp.append('{:%Y/%m/%d} * {}'.format(trn.date, trn.description))
            for spl in trn.splits:
                outp.append('\t{:50} {:12.2f} {} {}'.format(spl.account.fullname(),
                                                            spl.value,
                                                            spl.account.commodity,
                                                            '; ' + spl.memo if spl.memo else ''))
            outp.append('')

        return '\n'.join(outp)


class Commodity(object):
    """
    A commodity is something that's stored in GNU Cash accounts.

    Consists of a name (or id) and a space (namespace).
    """

    def __init__(self, name, space=None):
        self.name = name
        self.space = space

    def __str__(self):
        return self.name

    def __repr__(self):
        return "<Commodity {}:{}>".format(self.space, self.name)


class Account(object):
    """
    An account is part of a tree structure of accounts and contains splits.
    """

    def __init__(self, name, guid, actype, parent=None,
                 commodity=None, commodity_scu=None,
                 description=None, slots=None):
        self.name = name
        self.guid = guid
        self.actype = actype
        self.description = description
        self.parent = parent
        self.children = []
        self.commodity = commodity
        self.commodity_scu = commodity_scu
        self.splits = []
        self.slots = slots or {}

    def fullname(self):
        if self.parent:
            pfn = self.parent.fullname()
            if pfn:
                return '{}:{}'.format(pfn, self.name)
            else:
                return self.name
        else:
            return ''

    def __repr__(self):
        return "<Account '{}[{}]' {}...>".format(self.name, self.commodity, self.guid[:10])

    def walk(self):
        """
        Generate splits in this account tree by walking the tree.

        For each account, it yields a 3-tuple (account, subaccounts, splits).

        You can modify the list of subaccounts, but should not modify
        the list of splits.
        """
        accounts = [self]
        while accounts:
            acc, accounts = accounts[0], accounts[1:]
            children = list(acc.children)
            yield (acc, children, acc.splits)
            accounts.extend(children)

    def find_account(self, name):
        for account, children, splits in self.walk():
            if account.name == name:
                return account

    def get_all_splits(self):
        split_list = []
        for account, children, splits in self.walk():
            split_list.extend(splits)
        return sorted(split_list)

    def __lt__(self, other):
        # For sorted() only
        if isinstance(other, Account):
            return self.fullname() < other.fullname()
        else:
            False


class Transaction(object):
    """
    A transaction is a balanced group of splits.
    """

    def __init__(self, guid=None, currency=None,
                 date=None, date_entered=None,
                 description=None, splits=None,
                 num=None, slots=None):
        self.guid = guid
        self.currency = currency
        self.date = date
        self.post_date = date  # for compatibility with piecash
        self.date_entered = date_entered
        self.description = description
        self.num = num or None
        self.splits = splits or []
        self.slots = slots or {}

    def __repr__(self):
        return "<Transaction on {} '{}' {}...>".format(
            self.date, self.description, self.guid[:6])

    def __lt__(self, other):
        # For sorted() only
        if isinstance(other, Transaction):
            return self.date < other.date
        else:
            False


class Invoice(object):
    """
    An invoice is an grouping of data
    """

    def __init__(self, active=None, customer=None, id=None, date=None, entries=None, guid=None, vendor=None):
        self.active = active
        self.customer = customer
        self.date = date
        self.id = id
        self.entries = entries
        self.guid = guid
        self.vendor = vendor

    def __repr__(self):
        return "<Invoice id {} on {} (guid {})".format(
            self.id, self.date, self.guid)

    def __lt__(self, other):
        # For sorted() only
        if isinstance(other, Invoice):
            return self.date < other.date
        else:
            False


class Customer(object):
    """
    A customer
    """

    def __init__(self, guid=None, name=None, address=None):
        self.guid = guid
        self.name = name
        self.address = address

    def __repr__(self):
        return "<Customer {} (guid {})".format(self.name, self.guid)

    def __lt__(self, other):
        # For sorted() only
        if isinstance(other, Customer):
            return self.name < other.name
        else:
            False


class Entry(object):
    def __init__(self,
                 action=None,
                 description=None,
                 guid=None,
                 invoice_guid=None,
                 price=None,
                 qty=None,
                 taxable=None,
                 taxtable=None):
        self.action = action
        self.description = description
        self.guid = guid
        self.invoice_guid = invoice_guid
        self.price = price
        self.qty = qty
        self.taxable = taxable
        self.taxtable = taxtable

    def __repr__(self):
        return "<Entry {})".format(self.guid)

    def __lt__(self, other):
        # For sorted() only
        if isinstance(other, Entry):
            return self.guid < other.guid
        else:
            False


class Vendor(object):
    """
    A vendor
    """

    def __init__(self, guid=None, name=None):
        self.guid = guid
        self.name = name

    def __repr__(self):
        return "<Vendor {} (guid {})".format(self.name, self.guid)

    def __lt__(self, other):
        # For sorted() only
        if isinstance(other, Vendor):
            return self.name < other.name
        else:
            False


class Taxtableentry(object):
    def __init__(self, amount=None, ttetype=None):
        self.amount = amount
        self.ttetype = ttetype

    def __repr__(self):
        return "<Taxtableentry {} {})".format(self.amount, self.ttetype)

    def __lt__(self, other):
        # For sorted() only
        if isinstance(other, Taxtableentry):
            return self.amount < other.amount
        else:
            False


class Taxtable(object):
    def __init__(self, guid=None, name=None, taxtable_entries=None):
        self.guid = guid
        self.name = name
        self.taxtable_entries = taxtable_entries

    def __repr__(self):
        return "<Taxtable {} ({})".format(self.name, self.guid)

    def __lt__(self, other):
        # For sorted() only
        if isinstance(other, Taxtable):
            return self.name < other.name
        else:
            False


class Split(object):
    """
    A split is one entry in a transaction.
    """

    def __init__(self, guid=None, memo=None,
                 reconciled_state=None, reconcile_date=None, value=None,
                 quantity=None, account=None, transaction=None, action=None,
                 slots=None):
        self.guid = guid
        self.reconciled_state = reconciled_state
        self.reconcile_date = reconcile_date
        self.value = value
        self.quantity = quantity
        self.account = account
        self.transaction = transaction
        self.action = action
        self.memo = memo
        self.slots = slots

    def __repr__(self):
        return "<Split {} '{}' {} {} {}...>".format(self.transaction.date,
                                                    self.transaction.description,
                                                    self.transaction.currency,
                                                    self.value,
                                                    self.guid[:6])

    def __lt__(self, other):
        # For sorted() only
        if isinstance(other, Split):
            return self.transaction < other.transaction
        else:
            False


class Price(object):
    """
    A price is GNUCASH record of the price of a commodity against a currency
    Consists of date, currency, commodity,  value
    """

    def __init__(self, guid=None, commodity=None, currency=None,
                 date=None, value=None):
        self.guid = guid
        self.commodity = commodity
        self.currency = currency
        self.date = date
        self.value = value

    def __repr__(self):
        return "<Price {}... {:%Y/%m/%d}: {} {}/{} >".format(self.guid[:6],
                                                             self.date,
                                                             self.value,
                                                             self.commodity,
                                                             self.currency)

    def __lt__(self, other):
        # For sorted() only
        if isinstance(other, Price):
            return self.date < other.date
        else:
            False


##################################################################
# XML file parsing

def from_filename(filename):
    """Parse a GNU Cash file and return a Book object."""
    try:
        # try opening with gzip decompression
        return parse(gzip.open(filename, "rb"))
    except IOError:
        # try opening without decompression
        return parse(open(filename, "rb"))


# Implemented:
# - gnc:book
#
# Not implemented:
# - gnc:count-data
#   - This seems to be primarily for integrity checks?
def parse(fobj):
    """Parse GNU Cash XML data from a file object and return a Book object."""
    try:
        tree = ElementTree.parse(fobj)
    except ParseError:
        raise ValueError("File stream was not a valid GNU Cash v2 XML file")

    root = tree.getroot()
    if root.tag != 'gnc-v2':
        raise ValueError("File stream was not a valid GNU Cash v2 XML file")
    return _book_from_tree(root.find("{http://www.gnucash.org/XML/gnc}book"))


# Implemented:
# - book:id
# - book:slots
# - gnc:commodity
# - gnc:account
# - gnc:transaction
#
# Not implemented:
# - gnc:schedxaction
# - gnc:template-transactions
# - gnc:count-data
#   - This seems to be primarily for integrity checks?
def _book_from_tree(tree):
    guid = tree.find('{http://www.gnucash.org/XML/book}id').text

    # Implemented:
    # - cmdty:id
    # - cmdty:space
    #
    # Not implemented:
    # - cmdty:get_quotes => unknown, empty, optional
    # - cmdty:quote_tz => unknown, empty, optional
    # - cmdty:source => text, optional, e.g. "currency"
    # - cmdty:name => optional, e.g. "template"
    # - cmdty:xcode => optional, e.g. "template"
    # - cmdty:fraction => optional, e.g. "1"
    def _commodity_from_tree(tree):
        name = tree.find('{http://www.gnucash.org/XML/cmdty}id').text
        space = tree.find('{http://www.gnucash.org/XML/cmdty}space').text
        return Commodity(name=name, space=space)

    def _commodity_find(space, name):
        return commoditydict.setdefault((space, name), Commodity(name=name, space=space))

    commodities = []  # This will store the Gnucash root list of commodities
    commoditydict = {}  # This will store the list of commodities used
    # The above two may not be equal! eg prices may include commodities
    # that are not represented in the account tree

    for child in tree.findall('{http://www.gnucash.org/XML/gnc}commodity'):
        comm = _commodity_from_tree(child)
        commodities.append(_commodity_find(comm.space, comm.name))
        # COMPACT:
        # name = child.find('{http://www.gnucash.org/XML/cmdty}id').text
        # space = child.find('{http://www.gnucash.org/XML/cmdty}space').text
        # commodities.append(_commodity_find(space, name))

    # Implemented:
    # - price
    # - price:guid
    # - price:commodity
    # - price:currency
    # - price:date
    # - price:value
    def _price_from_tree(tree):
        price = '{http://www.gnucash.org/XML/price}'
        cmdty = '{http://www.gnucash.org/XML/cmdty}'
        ts = "{http://www.gnucash.org/XML/ts}"

        guid = tree.find(price + 'id').text
        value = _parse_number(tree.find(price + 'value').text)
        date = parse_date(tree.find(price + 'time/' + ts + 'date').text)

        currency_space = tree.find(price + "currency/" + cmdty + "space").text
        currency_name = tree.find(price + "currency/" + cmdty + "id").text
        currency = _commodity_find(currency_space, currency_name)

        commodity_space = tree.find(price + "commodity/" + cmdty + "space").text
        commodity_name = tree.find(price + "commodity/" + cmdty + "id").text
        commodity = _commodity_find(commodity_space, commodity_name)

        return Price(guid=guid,
                     commodity=commodity,
                     date=date,
                     value=value,
                     currency=currency)

    prices = []
    t = tree.find('{http://www.gnucash.org/XML/gnc}pricedb')
    if t is not None:
        for child in t.findall('price'):
            price = _price_from_tree(child)
            prices.append(price)

    root_account = None
    accounts = []
    accountdict = {}
    parentdict = {}

    for child in tree.findall('{http://www.gnucash.org/XML/gnc}account'):
        parent_guid, acc = _account_from_tree(child, commoditydict)
        if acc.actype == 'ROOT':
            root_account = acc
        accountdict[acc.guid] = acc
        parentdict[acc.guid] = parent_guid
    for acc in list(accountdict.values()):
        if acc.parent is None and acc.actype != 'ROOT':
            parent = accountdict[parentdict[acc.guid]]
            acc.parent = parent
            parent.children.append(acc)
            accounts.append(acc)

    transactions = []
    for child in tree.findall('{http://www.gnucash.org/XML/gnc}'
                              'transaction'):
        transactions.append(_transaction_from_tree(child,
                                                   accountdict,
                                                   commoditydict))

    customersdict = {}
    for child in tree.findall('{http://www.gnucash.org/XML/gnc}GncCustomer'):
        customer = _customer_from_tree(child)
        customersdict[customer.guid] = customer

    vendorsdict = {}
    for child in tree.findall('{http://www.gnucash.org/XML/gnc}GncVendor'):
        vendor = _vendor_from_tree(child)
        vendorsdict[vendor.guid] = vendor

    taxtablesdict = {}
    for child in tree.findall('{http://www.gnucash.org/XML/gnc}GncTaxTable'):
        taxtable = _taxtable_from_tree(child)
        taxtablesdict[taxtable.guid] = taxtable

    entriesdict = {}
    for child in tree.findall('{http://www.gnucash.org/XML/gnc}GncEntry'):
        entry = _entry_from_tree(child, taxtablesdict)
        entriesdict[entry.guid] = entry

    invoices = []
    for child in tree.findall('{http://www.gnucash.org/XML/gnc}GncInvoice'):
        invoices.append(_invoice_from_tree(child, customersdict, entriesdict, vendorsdict))

    slots = _slots_from_tree(
        tree.find('{http://www.gnucash.org/XML/book}slots'))
    return Book(tree=tree,
                guid=guid,
                prices=prices,
                transactions=transactions,
                root_account=root_account,
                accounts=accounts,
                commodities=commodities,
                slots=slots,
                invoices=invoices)


# Implemented:
# - act:name
# - act:id
# - act:type
# - act:description
# - act:commodity
# - act:commodity-scu
# - act:parent
# - act:slots
def _account_from_tree(tree, commoditydict):
    act = '{http://www.gnucash.org/XML/act}'
    cmdty = '{http://www.gnucash.org/XML/cmdty}'

    name = tree.find(act + 'name').text
    guid = tree.find(act + 'id').text
    actype = tree.find(act + 'type').text
    description = tree.find(act + "description")
    if description is not None:
        description = description.text
    slots = _slots_from_tree(tree.find(act + 'slots'))
    if actype == 'ROOT':
        parent_guid = None
        commodity = None
        commodity_scu = None
    else:
        parent_guid = tree.find(act + 'parent').text
        commodity_space = tree.find(act + 'commodity/' +
                                    cmdty + 'space').text
        commodity_name = tree.find(act + 'commodity/' +
                                   cmdty + 'id').text
        commodity_scu = tree.find(act + 'commodity-scu').text
        commodity = commoditydict[(commodity_space, commodity_name)]
    return parent_guid, Account(name=name,
                                description=description,
                                guid=guid,
                                actype=actype,
                                commodity=commodity,
                                commodity_scu=commodity_scu,
                                slots=slots)


# Implemented:
# - trn:id
# - trn:currency
# - trn:date-posted
# - trn:date-entered
# - trn:description
# - trn:splits / trn:split
# - trn:slots
def _transaction_from_tree(tree, accountdict, commoditydict):
    trn = '{http://www.gnucash.org/XML/trn}'
    cmdty = '{http://www.gnucash.org/XML/cmdty}'
    ts = '{http://www.gnucash.org/XML/ts}'

    guid = tree.find(trn + "id").text
    currency_space = tree.find(trn + "currency/" +
                               cmdty + "space").text
    currency_name = tree.find(trn + "currency/" +
                              cmdty + "id").text
    currency = commoditydict[(currency_space, currency_name)]
    date = parse_date(tree.find(trn + "date-posted/" +
                                ts + "date").text)
    date_entered = parse_date(tree.find(trn + "date-entered/" +
                                        ts + "date").text)
    description = tree.find(trn + "description").text

    # rarely used
    num = tree.find(trn + "num")
    if num is not None:
        num = num.text

    slots = _slots_from_tree(tree.find(trn + "slots"))
    transaction = Transaction(guid=guid,
                              currency=currency,
                              date=date,
                              date_entered=date_entered,
                              description=description,
                              num=num,
                              slots=slots)

    for subtree in tree.findall(trn + "splits/" + trn + "split"):
        split = _split_from_tree(subtree, accountdict, transaction)
        transaction.splits.append(split)

    return transaction


# Implemented:
# - entry:guid
# - entry:action
# - entry:description
# - entry:qty
# - entry:i-price
# - entry:invoice
# - entry:i-taxable
# - entry:i-taxtable
def _entry_from_tree(tree, taxtabledict):
    xml_entry = '{http://www.gnucash.org/XML/entry}'
    guid = tree.find(xml_entry + "guid").text
    action = None
    if tree.find(xml_entry + "action") is not None:
        action = tree.find(xml_entry + "action").text
    description = None
    if tree.find(xml_entry + "description") is not None:
        description = tree.find(xml_entry + "description").text
    qty = None
    if tree.find(xml_entry + "qty") is not None:
        qty = _parse_number(tree.find(xml_entry + "qty").text)
    price = None
    if tree.find(xml_entry + "i-price") is not None:
        price = _parse_number(tree.find(xml_entry + "i-price").text)
    invoice_guid = None
    if tree.find(xml_entry + "invoice") is not None:
        invoice_guid = tree.find(xml_entry + "invoice").text
    taxable = None
    taxtable = None
    if tree.find(xml_entry + "i-taxable") is not None:
        taxable = tree.find(xml_entry + "i-taxable").text
        taxtable_id = tree.find(xml_entry + "i-taxtable").text
        taxtable = taxtabledict[taxtable_id]
    entry = Entry(action=action,
                  description=description,
                  guid=guid,
                  invoice_guid=invoice_guid,
                  price=price,
                  qty=qty,
                  taxable=taxable,
                  taxtable=taxtable)
    return entry


# Implemented:
# - cust:guid
# - cust:name
# - cust:addr
def _customer_from_tree(tree):
    cust = '{http://www.gnucash.org/XML/cust}'
    addr = '{http://www.gnucash.org/XML/addr}'
    guid = tree.find(cust + "guid").text
    name = tree.find(cust + "name").text
    addr_tree = tree.find(cust + "addr")
    address = []
    if addr_tree.find(addr + "addr1") is not None:
        address.append(addr_tree.find(addr + "addr1").text)
    if addr_tree.find(addr + "addr2") is not None:
        address.append(addr_tree.find(addr + "addr2").text)
    if addr_tree.find(addr + "addr3") is not None:
        address.append(addr_tree.find(addr + "addr3").text)
    if addr_tree.find(addr + "addr4") is not None:
        address.append(addr_tree.find(addr + "addr4").text)

    customer = Customer(guid=guid, name=name, address=address)
    return customer


# Implemented:
# - vendor:guid
# - vendor:name
def _vendor_from_tree(tree):
    vend = '{http://www.gnucash.org/XML/vendor}'
    guid = tree.find(vend + "guid").text
    name = tree.find(vend + "name").text
    vendor = Vendor(guid=guid, name=name)
    return vendor


# Implemented:
# - tte:amount
# - tte:type
def _taxtableentry_from_tree(tree):
    tte = '{http://www.gnucash.org/XML/tte}'
    tte_amount = _parse_number(tree.find(tte + "amount").text)
    tte_type = tree.find(tte + "type").text
    taxtableentry = Taxtableentry(amount=tte_amount, ttetype=tte_type)
    return taxtableentry


# Implemented:
# - taxtable:guid
# - taxtable:name
# - taxtable:vendor
def _taxtable_from_tree(tree):
    taxtable = '{http://www.gnucash.org/XML/taxtable}'
    guid = tree.find(taxtable + "guid").text
    name = tree.find(taxtable + "name").text
    taxtable_entries_tree = tree.find(taxtable + "entries")
    taxtable_entries = []
    for child in taxtable_entries_tree:
        taxtable_entry = _taxtableentry_from_tree(child)
        taxtable_entries.append(taxtable_entry)

    # amount
    # type
    taxtable = Taxtable(guid=guid, name=name, taxtable_entries=taxtable_entries)
    return taxtable


#
# <gnc:GncTaxTable version="2.0.0">
#   <taxtable:guid type="guid">32176fc292851e1bbbc2c22e552bbe32</taxtable:guid>
#   <taxtable:name>BTW-verlegd-te-betalen</taxtable:name>
#   <taxtable:refcount>0</taxtable:refcount>
#   <taxtable:invisible>0</taxtable:invisible>
#   <taxtable:entries>
#     <gnc:GncTaxTableEntry>
#       <tte:acct type="guid">e9c9fc7db96bbe021a89fd5f46bd4de4</tte:acct>
#       <tte:amount>0/100000</tte:amount>
#       <tte:type>PERCENT</tte:type>
#     </gnc:GncTaxTableEntry>
#   </taxtable:entries>
# </gnc:GncTaxTable>


# Implemented:
# - invoice:guid
# - invoice:id
# - invoice:owner
# - invoice:posted / ts:date
def _invoice_from_tree(tree, customersdict, entriesdict, vendorsdict):
    invoice = '{http://www.gnucash.org/XML/invoice}'
    ts = '{http://www.gnucash.org/XML/ts}'
    owner = '{http://www.gnucash.org/XML/owner}'

    # from lxml import etree
    # print(etree.tostring(tree, pretty_print=True))
    # print("-------------------------------------------------------")

    guid = tree.find(invoice + "guid").text
    id = tree.find(invoice + "id").text
    date = parse_date((tree.find(invoice + "opened/" + ts + "date")).text)

    owner_tree = tree.find(invoice + "owner")
    owner_type = owner_tree.find(owner + "type").text
    owner_id = owner_tree.find(owner + "id").text

    # print owner_type
    # print owner_id

    customer = None
    vendor = None

    if owner_type == "gncCustomer":
        customer = customersdict[owner_id]
    if owner_type == "gncVendor":
        vendor = vendorsdict[owner_id]

    active = tree.find(invoice + "active").text

    entries = []
    for key in entriesdict.keys():
        entry = entriesdict[key]
        if entry.invoice_guid == guid:
            entries.append(entry)

    # posttxn = tree.find(invoice + "posttxn").text
    # print "posttxn {}".format(posttxn)
    # postlot = tree.find(invoice + "posttxn").text
    # postlot = tree.find(invoice + "posttxn").text
    # currency = tree.find(invoice + "currency")
    # < invoice:currency >
    # < cmdty:space > ISO4217 < / cmdty:space >
    # < cmdty:id > EUR < / cmdty:id >
    # < / invoice:currency >
    # slots = tree.find(invoice + "slots")
    # < invoice:slots >
    # < slot >
    # < slot:key > credit - note < / slot:key >
    # < slot:value
    # type = "integer" > 0 < / slot:value >
    # < / slot >
    # < / invoice:slots >

    # print "-------------------------------------------------------"

    invoice = Invoice(active=active, guid=guid, id=id, date=date, customer=customer, vendor=vendor, entries=entries)
    return invoice


# Implemented:
# - split:id
# - split:memo
# - split:reconciled-state
# - split:reconcile-date
# - split:value
# - split:quantity
# - split:account
# - split:slots
def _split_from_tree(tree, accountdict, transaction):
    split = '{http://www.gnucash.org/XML/split}'
    ts = "{http://www.gnucash.org/XML/ts}"

    guid = tree.find(split + "id").text
    memo = tree.find(split + "memo")
    if memo is not None:
        memo = memo.text
    reconciled_state = tree.find(split + "reconciled-state").text
    reconcile_date = tree.find(split + "reconcile-date/" + ts + "date")
    if reconcile_date is not None:
        reconcile_date = parse_date(reconcile_date.text)
    value = _parse_number(tree.find(split + "value").text)
    quantity = _parse_number(tree.find(split + "quantity").text)
    account_guid = tree.find(split + "account").text
    account = accountdict[account_guid]
    slots = _slots_from_tree(tree.find(split + "slots"))
    action = tree.find(split + "action")
    if action is not None:
        action = action.text

    split = Split(guid=guid,
                  memo=memo,
                  reconciled_state=reconciled_state,
                  reconcile_date=reconcile_date,
                  value=value,
                  quantity=quantity,
                  account=account,
                  transaction=transaction,
                  action=action,
                  slots=slots)
    account.splits.append(split)
    return split


# Implemented:
# - slot
# - slot:key
# - slot:value
# - ts:date
# - gdate
def _slots_from_tree(tree):
    if tree is None:
        return {}
    slot = "{http://www.gnucash.org/XML/slot}"
    ts = "{http://www.gnucash.org/XML/ts}"
    slots = {}
    for elt in tree.findall("slot"):
        key = elt.find(slot + "key").text
        value = elt.find(slot + "value")
        type_ = value.get('type', 'string')
        if type_ in ('integer', 'double'):
            slots[key] = int(value.text)
        elif type_ == 'numeric':
            slots[key] = _parse_number(value.text)
        elif type_ in ('string', 'guid'):
            slots[key] = value.text
        elif type_ == 'gdate':
            slots[key] = parse_date(value.find("gdate").text)
        elif type_ == 'timespec':
            slots[key] = parse_date(value.find(ts + "date").text)
        elif type_ == 'frame':
            slots[key] = _slots_from_tree(value)
        else:
            raise RuntimeError("Unknown slot type {}".format(type_))
    return slots


def _parse_number(numstring):
    num, denum = numstring.split("/")
    amount_dec = decimal.Decimal(num) / decimal.Decimal(denum)
    amount_dec = decimal.Decimal(str(amount_dec)).quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_UP)
    return amount_dec


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()
        if isinstance(o, decimal.Decimal):
            return float(o)
        return o.__dict__
