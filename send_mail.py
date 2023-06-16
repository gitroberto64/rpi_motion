import smtplib

        self.sendmail = options['motion']['sendmail']
        self.smtp = options['motion']['smtp']
        self.maillogin = options['motion']['maillogin']
        self.mailpassword = options['motion']['mailpassword']
        self.toaddress = options['motion']['toaddress']
            
            
            if self.sendmail:
                self.send_mail(filename)
    
    
    def send_mail(self, msg):
        try:
            fromaddr = self.maillogin
            toaddress = self.toaddress  
            password = self.mailpassword
            smtp = self.smtp
            message = 'Subject: {}\n\n{}'.format(socket.gethostname(), msg)
            server = smtplib.SMTP_SSL(smtp)  
            server.login(fromaddr, password)
            server.sendmail(fromaddr, toaddress, message)
            server.quit()
        except Exception as e:
            flush_print('Error send mail: ' + str(e))


 "sendmail": false, "smtp": "mail.linux.pl:465", "maillogin": "roberto@linux.pl", "mailpassword": "", "toaddress":"googrobbo@gmail.com" 
