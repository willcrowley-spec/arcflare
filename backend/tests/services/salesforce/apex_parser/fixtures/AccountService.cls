public class AccountService {
    @InvocableMethod(label='Update')
    public static void updateRatings(List<Account> accounts) {
        for (Account a : accounts) {
            a.Rating = 'Hot';
        }
        update accounts;
        List<Contact> cs = [SELECT Id FROM Contact WHERE AccountId IN :accounts];
        insert cs;
    }
}
