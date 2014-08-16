import os
import logging
from aleph.base import CollectorBase
from aleph.settings import SAMPLE_TEMP_DIR

class FileCollector(CollectorBase):

    required_options = [ 'path' ]

    def validate_options(self):
        super(FileCollector, self).validate_options()

        if not os.access(self.options['path'], os.R_OK):
            raise IOError('Path "%s" is not readable' % self.options['path'])
            

    def collect(self):
        try:
            for dirname, dirnames, filenames in os.walk(self.options['path']):
                for filename in filenames:
                    filepath = os.path.join(dirname, filename)
                    self.logger.debug("Collecting file %s from %s" % (filepath, self.options['path']))
                    self.create_sample(os.path.join(self.options['path'], filepath), filepath)
        except KeyboardInterrupt:
            pass

import email, imaplib, tempfile

class MailCollector(CollectorBase):

    imap_session = None

    default_options = {
        'ssl': True,
        'port': 993,
    }

    required_options = [ 'host','username','password','root_folder' ]

    def imap_login(self):
        # Log into IMAP
        if self.options['ssl']:
            self.imap_session = imaplib.IMAP4_SSL(self.options['host'], self.options['port'])
        else:
            self.imap_session = imaplib.IMAP4(self.options['host'], self.options['port'])

        rc, account = self.imap_session.login(self.options['username'], self.options['password'])

        if rc != 'OK':
            raise RuntimeError('Invalid credentials')

        # Set root folder for search
        self.imap_session.select(self.options['root_folder'])

    def process_message(self, message_parts):

        email_body = message_parts[0][1]
        mail = email.message_from_string(email_body)

        for part in mail.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue
            filename = part.get_filename()
 
            if bool(filename):
                temp_file = tempfile.NamedTemporaryFile(dir=SAMPLE_TEMP_DIR, suffix='_%s' % filename, delete=False)
                temp_file.write(part.get_payload(decode=True))
                self.create_sample(temp_file.name, mail['from'])

    def collect(self):

        try:
            rc, data = self.imap_session.search(None, '(UNSEEN)')
            if rc != 'OK':
                raise RuntimeError('Error searching folder %s' % self.options['root_folder'])

            # Iterate over all messages
            for message_id in data[0].split():
                rc, message_parts = self.imap_session.fetch(message_id, '(RFC822)')
                if rc != 'OK':
                    raise RuntimeError('Error fetching message.')

                self.process_message(message_parts)
                rc, flags_msg = self.imap_session.store(message_id, '+FLAGS', r'\Deleted')
                if rc != 'OK':
                    raise RuntimeError('Error deleting message')

            rc, ids = self.imap_session.expunge()
            if rc != 'OK':
                raise RuntimeError('Error running expunge')
            
        except Exception, e:
            raise


    def setup(self):
        try:
            self.imap_login()

        except Exception, e:
            return RuntimeError('Cannot connect to server: %s' % str(e))

    def teardown(self):
        if self.imap_session:
            self.imap_session.close()
            self.imap_session.logout()


COLLECTOR_MAP = {
    'local': FileCollector,
    'mail': MailCollector,
}