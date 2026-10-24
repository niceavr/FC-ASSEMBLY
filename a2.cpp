/* Input a number.To check and print the given number is +ve or -ve or Zero*/
#include<stdio.h>
int main()
{
 int n;
 printf("enter a number\n");
 scanf("%d",&n);
 if(n>0)
     printf("Positive");
else
  {
  	 if(n<0)
  	    printf("Negative");
  	 else
  	     printf("Zero");
  	
  	
  }
}
