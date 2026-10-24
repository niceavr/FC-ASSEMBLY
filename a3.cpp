/* Input a person age.To check and print the given person has eligible to vote or not*/
#include<stdio.h>
int main()
{
	int age;
	printf("Enter person age\n");
	scanf("%d",&age);
	if(age>=18)
	    printf("Eligible to vote");
	else
	    printf("not eligible to vote");
}
